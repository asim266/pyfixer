import os
import time
from flask import Flask, render_template, request, jsonify
import httpx
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration — Kimi K2.5 only
API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
API_BASE_URL = 'https://api.moonshot.ai/v1/chat/completions'
MODEL_NAME = 'kimi-k2.5'
MAX_TOKENS = 4000
TEMPERATURE = 1
FLASK_HOST = '0.0.0.0'
FLASK_PORT = int(os.environ.get('PORT', 5001))
MAX_CODE_LENGTH = 50000
MAX_ERROR_LENGTH = 5000
DAILY_REQUEST_LIMIT = int(os.environ.get('DAILY_LIMIT', 3))
SYSTEM_PROMPT = 'You are a Python code debugging expert. When asked to fix code, respond ONLY with the corrected Python code. No explanations, no markdown formatting, no backticks — just the raw working Python code.'

rate_limit_state = {'date': None, 'count': 0}


def check_rate_limit():
    today = date.today()
    if rate_limit_state['date'] != today:
        rate_limit_state['date'] = today
        rate_limit_state['count'] = 0
    if rate_limit_state['count'] >= DAILY_REQUEST_LIMIT:
        return False, 0
    rate_limit_state['count'] += 1
    return True, DAILY_REQUEST_LIMIT - rate_limit_state['count']


def validate_input(code, error_message):
    if len(code) > MAX_CODE_LENGTH:
        return f"Code is too long. Maximum allowed length is {MAX_CODE_LENGTH} characters."
    if len(error_message) > MAX_ERROR_LENGTH:
        return f"Error message is too long. Maximum allowed length is {MAX_ERROR_LENGTH} characters."
    return None


def call_kimi(prompt):
    """Call Kimi K2.5 API with retry on transient errors."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    }
    payload = {
        'model': MODEL_NAME,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': TEMPERATURE,
        'max_tokens': MAX_TOKENS,
    }
    last_error = None
    for attempt in range(3):
        response = httpx.post(API_BASE_URL, headers=headers, json=payload, timeout=120)
        if response.status_code == 429 and attempt < 2:
            time.sleep(3 * (attempt + 1))
            last_error = 'Rate limited — retrying...'
            continue
        data = response.json()
        if 'error' in data:
            raise Exception(data['error'].get('message', 'Unknown API error'))
        response.raise_for_status()
        content = data['choices'][0]['message']['content']
        if not content or not content.strip():
            raise Exception('Model returned an empty response. Please try again.')
        return content
    raise Exception(last_error or 'Request failed after retries.')


def strip_markdown_fences(code):
    code = code.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/debug', methods=['POST'])
def debug_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        code = data.get('code', '').strip()
        error = data.get('error', '').strip()

        if not code:
            return jsonify({'error': 'Python code is required'}), 400
        if not error:
            return jsonify({'error': 'Error message is required'}), 400
        if not API_KEY:
            return jsonify({'error': 'API key not configured.'}), 500

        validation_error = validate_input(code, error)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        allowed, remaining = check_rate_limit()
        if not allowed:
            return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT}/day). Try again tomorrow.'}), 429

        prompt = f"""I have Python code that's producing an error. Fix it.

**Original Code:**
```python
{code}
```

**Error Message:**
{error}

Respond with ONLY the fixed Python code. No explanations."""

        try:
            result = call_kimi(prompt)
            fixed_code = strip_markdown_fences(result)
        except Exception as e:
            rate_limit_state['count'] -= 1
            logger.error(f"Kimi API error: {e}")
            return jsonify({'error': str(e)}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'original_code': code,
            'error_message': error,
            'remaining_requests': remaining,
        })

    except Exception as e:
        logger.error(f"debug_code error: {e}")
        return jsonify({'error': f'Internal server error: {e}'}), 500


@app.route('/debug-generated', methods=['POST'])
def debug_generated_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        generated_code = data.get('generated_code', '').strip()
        new_error = data.get('new_error', '').strip()
        original_code = data.get('original_code', '').strip()
        original_error = data.get('original_error', '').strip()

        if not generated_code:
            return jsonify({'error': 'Generated code is required'}), 400
        if not new_error:
            return jsonify({'error': 'New error message is required'}), 400
        if not API_KEY:
            return jsonify({'error': 'API key not configured.'}), 500

        validation_error = validate_input(generated_code, new_error)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        allowed, remaining = check_rate_limit()
        if not allowed:
            return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT}/day). Try again tomorrow.'}), 429

        prompt = f"""I previously had code that was producing an error, and you fixed it. However, the fixed code now has a new error.

**Original Code:**
```python
{original_code}
```

**Original Error:** {original_error}

**Previously Fixed Code (now has a new error):**
```python
{generated_code}
```

**New Error:** {new_error}

Respond with ONLY the corrected Python code. No explanations."""

        try:
            result = call_kimi(prompt)
            fixed_code = strip_markdown_fences(result)
        except Exception as e:
            rate_limit_state['count'] -= 1
            logger.error(f"Kimi API error (re-debug): {e}")
            return jsonify({'error': str(e)}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'generated_code': generated_code,
            'new_error_message': new_error,
            'iteration': 'recursive_debug',
            'remaining_requests': remaining,
        })

    except Exception as e:
        logger.error(f"debug_generated error: {e}")
        return jsonify({'error': f'Internal server error: {e}'}), 500


@app.route('/rate-limit-status')
def rate_limit_status():
    today = date.today()
    used = rate_limit_state['count'] if rate_limit_state['date'] == today else 0
    return jsonify({
        'daily_limit': DAILY_REQUEST_LIMIT,
        'used_today': used,
        'remaining': DAILY_REQUEST_LIMIT - used,
    })


@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'model': MODEL_NAME,
        'api_key_status': 'configured' if API_KEY else 'missing',
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print(f"API key: {'configured' if API_KEY else 'MISSING!'}")
    print(f"Model: {MODEL_NAME}")
    print(f"Rate limit: {DAILY_REQUEST_LIMIT} requests/day")
    print(f"Starting PyFixer on http://localhost:{FLASK_PORT}")
    app.run(debug=True, host=FLASK_HOST, port=FLASK_PORT)
