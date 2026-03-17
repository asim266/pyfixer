import os
from flask import Flask, render_template, request, jsonify
import httpx
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# ── Provider Registry ──
# Each provider: env var for key, base URL, and available models.
# Only providers with a configured API key will be shown to users.
PROVIDERS = {
    'groq': {
        'name': 'Groq',
        'env_key': 'GROQ_API_KEY',
        'base_url': 'https://api.groq.com/openai/v1/chat/completions',
        'models': [
            {'id': 'llama-3.3-70b-versatile', 'label': 'Llama 3.3 70B'},
            {'id': 'llama-3.1-8b-instant', 'label': 'Llama 3.1 8B'},
            {'id': 'gemma2-9b-it', 'label': 'Gemma 2 9B'},
        ],
    },
    'cerebras': {
        'name': 'Cerebras',
        'env_key': 'CEREBRAS_API_KEY',
        'base_url': 'https://api.cerebras.ai/v1/chat/completions',
        'models': [
            {'id': 'llama3.1-8b', 'label': 'Llama 3.1 8B'},
        ],
    },
    'sambanova': {
        'name': 'SambaNova',
        'env_key': 'SAMBANOVA_API_KEY',
        'base_url': 'https://api.sambanova.ai/v1/chat/completions',
        'models': [
            {'id': 'Meta-Llama-3.3-70B-Instruct', 'label': 'Llama 3.3 70B'},
            {'id': 'Meta-Llama-3.1-8B-Instruct', 'label': 'Llama 3.1 8B'},
        ],
    },
    'openrouter': {
        'name': 'OpenRouter',
        'env_key': 'OPENROUTER_API_KEY',
        'base_url': 'https://openrouter.ai/api/v1/chat/completions',
        'models': [
            {'id': 'meta-llama/llama-3.3-70b-instruct:free', 'label': 'Llama 3.3 70B'},
            {'id': 'mistralai/mistral-small-3.1-24b-instruct:free', 'label': 'Mistral Small 3.1 24B'},
            {'id': 'google/gemma-3-27b-it:free', 'label': 'Gemma 3 27B'},
        ],
    },
    'moonshot': {
        'name': 'Moonshot',
        'env_key': 'MOONSHOT_API_KEY',
        'base_url': 'https://api.moonshot.cn/v1/chat/completions',
        'models': [
            {'id': 'moonshot-v1-32k', 'label': 'Moonshot V1 32K'},
        ],
    },
}

FLASK_HOST = '0.0.0.0'
FLASK_PORT = int(os.environ.get('PORT', 5001))
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
MAX_CODE_LENGTH = 50000
MAX_ERROR_LENGTH = 5000
DAILY_REQUEST_LIMIT = int(os.environ.get('DAILY_LIMIT', 20))
SYSTEM_PROMPT = 'You are a Python code debugging expert. When asked to fix code, respond ONLY with the corrected Python code. No explanations, no markdown formatting, no backticks — just the raw working Python code.'

rate_limit_state = {'date': None, 'count': 0}


def get_available_providers():
    """Return providers that have API keys configured."""
    available = {}
    for key, provider in PROVIDERS.items():
        api_key = os.environ.get(provider['env_key'], '')
        if api_key:
            available[key] = {
                'name': provider['name'],
                'models': provider['models'],
            }
    return available


def resolve_provider(provider_key, model_id):
    """Resolve provider config + API key. Returns (base_url, api_key, model_id) or None."""
    provider = PROVIDERS.get(provider_key)
    if not provider:
        return None
    api_key = os.environ.get(provider['env_key'], '')
    if not api_key:
        return None
    valid_ids = [m['id'] for m in provider['models']]
    if model_id not in valid_ids:
        model_id = valid_ids[0]
    return provider['base_url'], api_key, model_id


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


def call_llm(base_url, api_key, model_id, prompt):
    """Call any OpenAI-compatible chat completions endpoint."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.3,
        'max_tokens': 4000,
    }
    response = httpx.post(base_url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']


def strip_markdown_fences(code):
    code = code.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


def do_debug(prompt, provider_key, model_id):
    """Run a debug prompt against the selected provider. Returns (fixed_code, error_string)."""
    resolved = resolve_provider(provider_key, model_id)
    if not resolved:
        return None, f'Provider "{provider_key}" is not configured.'
    base_url, api_key, model_id = resolved
    try:
        result = call_llm(base_url, api_key, model_id, prompt)
        return strip_markdown_fences(result), None
    except httpx.HTTPStatusError as e:
        logger.error(f"API HTTP error ({provider_key}): {e.response.status_code}")
        if e.response.status_code == 401:
            return None, 'Invalid API key for this provider.'
        if e.response.status_code == 429:
            return None, 'Provider rate limit exceeded. Try another model or wait.'
        return None, f'API error (status {e.response.status_code}).'
    except Exception as e:
        logger.error(f"API error ({provider_key}): {e}")
        return None, f'Could not process: {e}'


# ── Routes ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/providers')
def providers():
    return jsonify(get_available_providers())


@app.route('/debug', methods=['POST'])
def debug_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        code = data.get('code', '').strip()
        error = data.get('error', '').strip()
        provider_key = data.get('provider', '')
        model_id = data.get('model', '')

        if not code:
            return jsonify({'error': 'Python code is required'}), 400
        if not error:
            return jsonify({'error': 'Error message is required'}), 400
        if not provider_key or not model_id:
            return jsonify({'error': 'Please select a model'}), 400

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

        fixed_code, err = do_debug(prompt, provider_key, model_id)
        if err:
            rate_limit_state['count'] -= 1
            return jsonify({'error': err}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'original_code': code,
            'error_message': error,
            'remaining_requests': remaining,
            'model_used': model_id,
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
        provider_key = data.get('provider', '')
        model_id = data.get('model', '')

        if not generated_code:
            return jsonify({'error': 'Generated code is required'}), 400
        if not new_error:
            return jsonify({'error': 'New error message is required'}), 400
        if not provider_key or not model_id:
            return jsonify({'error': 'Please select a model'}), 400

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

        fixed_code, err = do_debug(prompt, provider_key, model_id)
        if err:
            rate_limit_state['count'] -= 1
            return jsonify({'error': err}), 500

        return jsonify({
            'success': True,
            'fixed_code': fixed_code,
            'generated_code': generated_code,
            'new_error_message': new_error,
            'iteration': 'recursive_debug',
            'remaining_requests': remaining,
            'model_used': model_id,
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
    available = list(get_available_providers().keys())
    return jsonify({
        'status': 'healthy',
        'providers': available,
        'provider_count': len(available),
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    avail = get_available_providers()
    print(f"Providers configured: {', '.join(avail.keys()) or 'NONE'}")
    print(f"Rate limit: {DAILY_REQUEST_LIMIT} requests/day")
    print(f"Starting PyFixer on http://localhost:{FLASK_PORT}")
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)
