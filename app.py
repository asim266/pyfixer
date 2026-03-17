import os
from flask import Flask, render_template, request, jsonify
import httpx
import json
import logging
from datetime import date

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
API_BASE_URL = 'https://api.moonshot.cn/v1/chat/completions'
MODEL_NAME = 'moonshot-v1-32k'
MAX_TOKENS = 4000
TEMPERATURE = 0.3
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5001
FLASK_DEBUG = True
APP_NAME = 'Python Code Debugger'
MAX_CODE_LENGTH = 50000
MAX_ERROR_LENGTH = 5000

# Rate limiting: 2 requests per day
DAILY_REQUEST_LIMIT = 2
rate_limit_state = {'date': None, 'count': 0}


def check_rate_limit():
    """Check and update daily rate limit. Returns (allowed, remaining)."""
    today = date.today()
    if rate_limit_state['date'] != today:
        rate_limit_state['date'] = today
        rate_limit_state['count'] = 0

    if rate_limit_state['count'] >= DAILY_REQUEST_LIMIT:
        return False, 0

    rate_limit_state['count'] += 1
    remaining = DAILY_REQUEST_LIMIT - rate_limit_state['count']
    return True, remaining


def validate_input(code, error_message):
    """Validate input parameters"""
    if len(code) > MAX_CODE_LENGTH:
        return f"Code is too long. Maximum allowed length is {MAX_CODE_LENGTH} characters."
    if len(error_message) > MAX_ERROR_LENGTH:
        return f"Error message is too long. Maximum allowed length is {MAX_ERROR_LENGTH} characters."
    return None


def call_moonshot_api(prompt):
    """Call the Moonshot AI API with the given prompt."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    }
    payload = {
        'model': MODEL_NAME,
        'messages': [
            {
                'role': 'system',
                'content': 'You are a Python code debugging expert. When asked to fix code, respond ONLY with the corrected Python code. No explanations, no markdown formatting, no backticks — just the raw working Python code.'
            },
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'temperature': TEMPERATURE,
        'max_tokens': MAX_TOKENS,
    }

    response = httpx.post(API_BASE_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']


def strip_markdown_fences(code):
    """Remove markdown code fences if present."""
    code = code.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


def fix_python_code(code, error_message):
    """Use Moonshot AI to fix Python code based on the error message."""
    if not API_KEY:
        return "Error: Moonshot API key not configured."

    validation_error = validate_input(code, error_message)
    if validation_error:
        return f"Error: {validation_error}"

    try:
        prompt = f"""I have Python code that's producing an error. Fix it.

**Original Code:**
```python
{code}
```

**Error Message:**
{error_message}

Respond with ONLY the fixed Python code. No explanations."""

        result = call_moonshot_api(prompt)
        return strip_markdown_fences(result)

    except httpx.HTTPStatusError as e:
        logger.error(f"Moonshot API HTTP error: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 401:
            return "Error: Invalid API key. Please check your Moonshot API key."
        elif e.response.status_code == 429:
            return "Error: API rate limit exceeded. Please try again later."
        return f"Error: API returned status {e.response.status_code}."
    except Exception as e:
        logger.error(f"Error calling Moonshot API: {str(e)}")
        return f"Error: Could not process the code. {str(e)}"


@app.route('/')
def index():
    """Main page with code input form"""
    return render_template('index.html')


@app.route('/debug', methods=['POST'])
def debug_code():
    """Endpoint to debug Python code"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        python_code = data.get('code', '').strip()
        error_message = data.get('error', '').strip()

        if not python_code:
            return jsonify({'error': 'Python code is required'}), 400
        if not error_message:
            return jsonify({'error': 'Error message is required'}), 400
        if not API_KEY:
            return jsonify({'error': 'Moonshot API key not configured.'}), 500

        validation_error = validate_input(python_code, error_message)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        # Rate limit check
        allowed, remaining = check_rate_limit()
        if not allowed:
            return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT} requests/day). Try again tomorrow.'}), 429

        fixed_code = fix_python_code(python_code, error_message)

        if fixed_code.startswith("Error:"):
            # Undo rate limit count on API failure
            rate_limit_state['count'] -= 1
            return jsonify({'error': fixed_code}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'original_code': python_code,
            'error_message': error_message,
            'remaining_requests': remaining,
        })

    except Exception as e:
        logger.error(f"Error in debug_code endpoint: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/debug-generated', methods=['POST'])
def debug_generated_code():
    """Endpoint to debug previously generated/fixed code"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        generated_code = data.get('generated_code', '').strip()
        new_error_message = data.get('new_error', '').strip()
        original_code = data.get('original_code', '').strip()
        original_error = data.get('original_error', '').strip()

        if not generated_code:
            return jsonify({'error': 'Generated code is required'}), 400
        if not new_error_message:
            return jsonify({'error': 'New error message is required'}), 400
        if not API_KEY:
            return jsonify({'error': 'Moonshot API key not configured.'}), 500

        validation_error = validate_input(generated_code, new_error_message)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        # Rate limit check
        allowed, remaining = check_rate_limit()
        if not allowed:
            return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT} requests/day). Try again tomorrow.'}), 429

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

**New Error:** {new_error_message}

Respond with ONLY the corrected Python code. No explanations."""

        try:
            result = call_moonshot_api(prompt)
            fixed_code = strip_markdown_fences(result)
        except Exception as e:
            logger.error(f"Moonshot API error for recursive debug: {str(e)}")
            rate_limit_state['count'] -= 1
            return jsonify({'error': f'Error: Could not process the code. {str(e)}'}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'generated_code': generated_code,
            'new_error_message': new_error_message,
            'iteration': 'recursive_debug',
            'remaining_requests': remaining,
        })

    except Exception as e:
        logger.error(f"Error in debug_generated_code endpoint: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/rate-limit-status')
def rate_limit_status():
    """Check remaining daily requests"""
    today = date.today()
    if rate_limit_state['date'] != today:
        used = 0
    else:
        used = rate_limit_state['count']
    return jsonify({
        'daily_limit': DAILY_REQUEST_LIMIT,
        'used_today': used,
        'remaining': DAILY_REQUEST_LIMIT - used,
    })


@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Python Code Debugger API is running',
        'api_key_status': 'configured' if API_KEY else 'missing',
        'model': MODEL_NAME,
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    if API_KEY:
        print(f"API key: configured (Moonshot AI)")
    else:
        print("WARNING: MOONSHOT_API_KEY not set!")
    print(f"Model: {MODEL_NAME}")
    print(f"Rate limit: {DAILY_REQUEST_LIMIT} requests/day")
    print(f"Starting {APP_NAME} on http://localhost:{FLASK_PORT}")
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)
