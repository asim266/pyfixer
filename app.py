import os
import time
import re
from flask import Flask, render_template, request, jsonify
import httpx
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(32).hex())

# ── Default config (Kimi K2.5) ──
DEFAULT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
DEFAULT_BASE_URL = 'https://api.moonshot.ai/v1/chat/completions'
DEFAULT_MODEL = 'kimi-k2.5'
FLASK_HOST = '0.0.0.0'
FLASK_PORT = int(os.environ.get('PORT', 5001))
MAX_CODE_LENGTH = 50000
MAX_ERROR_LENGTH = 5000
DAILY_REQUEST_LIMIT = int(os.environ.get('DAILY_LIMIT', 3))

# ── BYOK Provider Registry ──
BYOK_PROVIDERS = {
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1/chat/completions',
        'models': [
            {'id': 'gpt-4o', 'label': 'GPT-4o'},
            {'id': 'gpt-4o-mini', 'label': 'GPT-4o Mini'},
            {'id': 'gpt-4.1-mini', 'label': 'GPT-4.1 Mini'},
            {'id': 'gpt-4.1-nano', 'label': 'GPT-4.1 Nano'},
        ],
        'key_prefix': 'sk-',
        'signup_url': 'https://platform.openai.com/api-keys',
    },
    'groq': {
        'name': 'Groq',
        'base_url': 'https://api.groq.com/openai/v1/chat/completions',
        'models': [
            {'id': 'llama-3.3-70b-versatile', 'label': 'Llama 3.3 70B'},
            {'id': 'llama-3.1-8b-instant', 'label': 'Llama 3.1 8B'},
            {'id': 'gemma2-9b-it', 'label': 'Gemma 2 9B'},
        ],
        'key_prefix': 'gsk_',
        'signup_url': 'https://console.groq.com',
    },
    'openrouter': {
        'name': 'OpenRouter',
        'base_url': 'https://openrouter.ai/api/v1/chat/completions',
        'models': [
            {'id': 'meta-llama/llama-3.3-70b-instruct:free', 'label': 'Llama 3.3 70B (Free)'},
            {'id': 'mistralai/mistral-small-3.1-24b-instruct:free', 'label': 'Mistral Small 3.1 (Free)'},
            {'id': 'moonshotai/kimi-k2-0905', 'label': 'Kimi K2'},
            {'id': 'openai/gpt-4o', 'label': 'GPT-4o'},
            {'id': 'anthropic/claude-sonnet-4', 'label': 'Claude Sonnet 4'},
        ],
        'key_prefix': 'sk-or-',
        'signup_url': 'https://openrouter.ai/settings/keys',
    },
    'moonshot': {
        'name': 'Moonshot / Kimi',
        'base_url': 'https://api.moonshot.ai/v1/chat/completions',
        'models': [
            {'id': 'kimi-k2.5', 'label': 'Kimi K2.5'},
            {'id': 'moonshot-v1-32k', 'label': 'Moonshot V1 32K'},
        ],
        'key_prefix': 'sk-',
        'signup_url': 'https://platform.moonshot.ai/console/api-keys',
    },
    'gemini': {
        'name': 'Google Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
        'models': [
            {'id': 'gemini-2.5-flash', 'label': 'Gemini 2.5 Flash'},
            {'id': 'gemini-2.5-pro', 'label': 'Gemini 2.5 Pro'},
        ],
        'key_prefix': 'AI',
        'signup_url': 'https://aistudio.google.com/apikey',
    },
}

SYSTEM_PROMPT = '''You are a Python code debugging expert.
Given buggy Python code and its error message, return a JSON object with exactly two keys:
- "fixed_code": the corrected Python code (no markdown fences, just raw code)
- "explanation": a brief 1-2 sentence explanation of what was wrong and what you changed

Return ONLY valid JSON. No markdown, no extra text.'''

# ── Per-IP rate limiting ──
ip_rate_limits = {}


def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()


def check_rate_limit():
    """Per-IP daily rate limit. Returns (allowed, remaining)."""
    ip = get_client_ip()
    today = date.today()
    if ip not in ip_rate_limits or ip_rate_limits[ip]['date'] != today:
        ip_rate_limits[ip] = {'date': today, 'count': 0}
    state = ip_rate_limits[ip]
    if state['count'] >= DAILY_REQUEST_LIMIT:
        return False, 0
    state['count'] += 1
    return True, DAILY_REQUEST_LIMIT - state['count']


def undo_rate_limit():
    ip = get_client_ip()
    if ip in ip_rate_limits:
        ip_rate_limits[ip]['count'] = max(0, ip_rate_limits[ip]['count'] - 1)


def validate_input(code, error_message):
    if len(code) > MAX_CODE_LENGTH:
        return f"Code is too long. Maximum {MAX_CODE_LENGTH} characters."
    if len(error_message) > MAX_ERROR_LENGTH:
        return f"Error message is too long. Maximum {MAX_ERROR_LENGTH} characters."
    return None


def sanitize_for_prompt(text):
    """Basic prompt injection protection — escape instruction-like patterns."""
    blocklist = [
        r'ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts)',
        r'disregard\s+(all\s+)?(previous|above)',
        r'you\s+are\s+now',
        r'new\s+instructions?:',
        r'system\s*:',
    ]
    sanitized = text
    for pattern in blocklist:
        sanitized = re.sub(pattern, '[FILTERED]', sanitized, flags=re.IGNORECASE)
    return sanitized


def call_llm(base_url, api_key, model_id, prompt):
    """Call any OpenAI-compatible endpoint with retry."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    # Kimi K2.5 requires temperature=1
    temp = 1 if 'kimi' in model_id.lower() else 0.3
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': temp,
        'max_tokens': 4000,
    }
    last_error = None
    for attempt in range(3):
        response = httpx.post(base_url, headers=headers, json=payload, timeout=120)
        if response.status_code == 429 and attempt < 2:
            time.sleep(3 * (attempt + 1))
            last_error = 'Rate limited — retrying...'
            continue
        data = response.json()
        if 'error' in data:
            err_code = data['error'].get('code', response.status_code)
            if err_code == 429 and attempt < 2:
                last_error = data['error'].get('message', 'Rate limited')
                time.sleep(3 * (attempt + 1))
                continue
            raise Exception(data['error'].get('message', 'Unknown API error'))
        response.raise_for_status()
        content = data['choices'][0]['message']['content']
        if not content or not content.strip():
            raise Exception('Model returned an empty response. Try a different model.')
        return content
    raise Exception(last_error or 'Request failed after retries.')


def parse_llm_response(raw):
    """Parse JSON response from LLM, with fallback for plain code."""
    import json
    raw = raw.strip()
    # Strip markdown fences if present
    if raw.startswith('```json'):
        raw = raw[7:]
    if raw.startswith('```'):
        raw = raw[3:]
    if raw.endswith('```'):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        code = parsed.get('fixed_code', '').strip()
        explanation = parsed.get('explanation', '').strip()
        # Strip fences from code if model still added them
        if code.startswith('```python'):
            code = code[9:]
        if code.startswith('```'):
            code = code[3:]
        if code.endswith('```'):
            code = code[:-3]
        return code.strip(), explanation
    except (json.JSONDecodeError, AttributeError):
        # Fallback: treat as plain code
        code = raw
        if code.startswith('```python'):
            code = code[9:]
        if code.startswith('```'):
            code = code[3:]
        if code.endswith('```'):
            code = code[:-3]
        return code.strip(), ''


def resolve_request(data):
    """Resolve provider config from request. Returns (base_url, api_key, model_id, is_byok)."""
    user_key = (data.get('api_key') or '').strip()
    provider_key = (data.get('provider') or '').strip()
    model_id = (data.get('model') or '').strip()

    if user_key and provider_key:
        provider = BYOK_PROVIDERS.get(provider_key)
        if not provider:
            return None, None, None, True
        if not model_id:
            model_id = provider['models'][0]['id']
        return provider['base_url'], user_key, model_id, True

    # Default: use server Kimi K2.5
    return DEFAULT_BASE_URL, DEFAULT_API_KEY, DEFAULT_MODEL, False


# ── Routes ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/byok-providers')
def byok_providers():
    return jsonify(BYOK_PROVIDERS)


@app.route('/debug', methods=['POST'])
def debug_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        code = (data.get('code') or '').strip()
        error = (data.get('error') or '').strip()

        if not code:
            return jsonify({'error': 'Python code is required'}), 400
        if not error:
            return jsonify({'error': 'Error message is required'}), 400

        validation_error = validate_input(code, error)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        base_url, api_key, model_id, is_byok = resolve_request(data)

        if not api_key:
            return jsonify({'error': 'No API key available. Use your own key or try later.'}), 400

        # Rate limit only for default key (not BYOK)
        remaining = None
        if not is_byok:
            allowed, remaining = check_rate_limit()
            if not allowed:
                return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT}/day). Use your own API key for unlimited access.'}), 429

        safe_code = sanitize_for_prompt(code)
        safe_error = sanitize_for_prompt(error)

        prompt = f"""Fix this Python code:

<code>
{safe_code}
</code>

<error>
{safe_error}
</error>

Return JSON: {{"fixed_code": "...", "explanation": "..."}}"""

        try:
            raw = call_llm(base_url, api_key, model_id, prompt)
            fixed_code, explanation = parse_llm_response(raw)
        except Exception as e:
            if not is_byok:
                undo_rate_limit()
            logger.error(f"LLM error: {e}")
            return jsonify({'error': str(e)}), 500

        if not fixed_code:
            if not is_byok:
                undo_rate_limit()
            return jsonify({'error': 'Model returned empty code. Try again.'}), 500

        result = {
            'success': True,
            'fixed_code': fixed_code,
            'explanation': explanation,
            'original_code': code,
            'error_message': error,
            'model_used': model_id,
        }
        if remaining is not None:
            result['remaining_requests'] = remaining
        return jsonify(result)

    except Exception as e:
        logger.error(f"debug_code error: {e}")
        return jsonify({'error': f'Internal server error: {e}'}), 500


@app.route('/debug-generated', methods=['POST'])
def debug_generated_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        generated_code = (data.get('generated_code') or '').strip()
        new_error = (data.get('new_error') or '').strip()
        original_code = (data.get('original_code') or '').strip()
        original_error = (data.get('original_error') or '').strip()

        if not generated_code:
            return jsonify({'error': 'Generated code is required'}), 400
        if not new_error:
            return jsonify({'error': 'New error message is required'}), 400

        validation_error = validate_input(generated_code, new_error)
        if validation_error:
            return jsonify({'error': validation_error}), 400

        base_url, api_key, model_id, is_byok = resolve_request(data)

        if not api_key:
            return jsonify({'error': 'No API key available.'}), 400

        remaining = None
        if not is_byok:
            allowed, remaining = check_rate_limit()
            if not allowed:
                return jsonify({'error': f'Daily limit reached ({DAILY_REQUEST_LIMIT}/day). Use your own API key for unlimited access.'}), 429

        prompt = f"""Previously fixed code still has an error. Fix it again.

<original_code>
{sanitize_for_prompt(original_code)}
</original_code>

<original_error>
{sanitize_for_prompt(original_error)}
</original_error>

<fixed_code_with_new_error>
{sanitize_for_prompt(generated_code)}
</fixed_code_with_new_error>

<new_error>
{sanitize_for_prompt(new_error)}
</new_error>

Return JSON: {{"fixed_code": "...", "explanation": "..."}}"""

        try:
            raw = call_llm(base_url, api_key, model_id, prompt)
            fixed_code, explanation = parse_llm_response(raw)
        except Exception as e:
            if not is_byok:
                undo_rate_limit()
            logger.error(f"LLM re-debug error: {e}")
            return jsonify({'error': str(e)}), 500

        result = {
            'success': True,
            'fixed_code': fixed_code,
            'explanation': explanation,
            'generated_code': generated_code,
            'new_error_message': new_error,
            'iteration': 'recursive_debug',
            'model_used': model_id,
        }
        if remaining is not None:
            result['remaining_requests'] = remaining
        return jsonify(result)

    except Exception as e:
        logger.error(f"debug_generated error: {e}")
        return jsonify({'error': f'Internal server error: {e}'}), 500


@app.route('/rate-limit-status')
def rate_limit_status():
    ip = get_client_ip()
    today = date.today()
    state = ip_rate_limits.get(ip, {'date': None, 'count': 0})
    used = state['count'] if state['date'] == today else 0
    return jsonify({
        'daily_limit': DAILY_REQUEST_LIMIT,
        'used_today': used,
        'remaining': DAILY_REQUEST_LIMIT - used,
    })


@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'model': DEFAULT_MODEL,
        'api_key_status': 'configured' if DEFAULT_API_KEY else 'missing',
        'byok_providers': list(BYOK_PROVIDERS.keys()),
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print(f"Default key: {'configured' if DEFAULT_API_KEY else 'MISSING!'}")
    print(f"Default model: {DEFAULT_MODEL}")
    print(f"BYOK providers: {', '.join(BYOK_PROVIDERS.keys())}")
    print(f"Rate limit: {DAILY_REQUEST_LIMIT}/day per IP")
    print(f"Starting PyFixer on http://localhost:{FLASK_PORT}")
    app.run(debug=True, host=FLASK_HOST, port=FLASK_PORT)
