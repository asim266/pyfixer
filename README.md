# Python Code Debugger - AI Powered

An intelligent Python code debugging tool powered by Claude Opus API. Simply paste your Python code and error message to get instant AI-powered fixes!

## Features

🐛 **AI-Powered Debugging**: Uses Claude Opus to analyze and fix Python code errors
🚀 **Simple Interface**: Clean, modern Bootstrap-based UI
📝 **Syntax Highlighting**: Code is displayed with proper Python syntax highlighting
📋 **Copy & Download**: Easy copy-to-clipboard and download functionality
🔄 **Recursive Debugging**: Debug generated code again if it still has errors
⚡ **Zero Setup**: No configuration needed - API key included
💻 **Responsive Design**: Works perfectly on desktop and mobile devices

## Screenshots

The application features a modern, clean interface with:
- Code input area with syntax highlighting
- Error message input field
- AI-powered code fixing
- Results display with copy/download options
- Recursive debugging option for generated code

## Installation

### Prerequisites

- Python 3.7 or higher

### Setup Steps

1. **Clone or download the project**
   ```bash
   cd python_code_debugger
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

That's it! No configuration needed.

## Usage

### Running the Application

1. **Start the Flask server**
   ```bash
   python app.py
   ```

2. **Open your browser**
   Navigate to `http://localhost:5000`

3. **Use the debugger**
   - Paste your Python code in the first text area
   - Paste the error message in the second text area
   - Click "Fix My Code"
   - Get your corrected Python code instantly!

4. **Recursive debugging**
   - If the generated code still has errors, click "Debug Generated Code"
   - Enter the new error message
   - Get an improved fix that considers both the original and new errors

### Example Usage

**Input Code:**
```python
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)

numbers = [1, 2, 3, 4, 5]
result = calculate_average()
print(f"Average: {result}")
```

**Error Message:**
```
TypeError: calculate_average() missing 1 required positional argument: 'numbers'
```

**Fixed Code Output:**
```python
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)

numbers = [1, 2, 3, 4, 5]
result = calculate_average(numbers)  # Fixed: Added missing argument
print(f"Average: {result}")
```

## API Endpoints

### `POST /debug`

Fix Python code using Claude AI.

**Request Body:**
```json
{
    "code": "your_python_code_here",
    "error": "error_message_here"
}
```

### `POST /debug-generated`

Debug previously generated/fixed code with recursive context.

**Request Body:**
```json
{
    "generated_code": "previously_fixed_code",
    "new_error": "new_error_message",
    "original_code": "original_code",
    "original_error": "original_error"
}
```

### `GET /health`

Health check endpoint showing API key status.

## Error Handling

The application includes comprehensive error handling for:

- **Invalid Input**: Validation for code/error length limits
- **API Failures**: Graceful handling of Claude API errors
- **Network Issues**: Proper error messages for connection problems

## Technical Details

### Tech Stack

- **Backend**: Flask with zero configuration
- **Frontend**: Bootstrap 5, Prism.js for syntax highlighting
- **AI**: Claude Opus via Anthropic API
- **Configuration**: All settings hardcoded in app.py

### File Structure

```
python_code_debugger/
├── app.py                 # Main Flask application (includes API key)
├── requirements.txt      # Python dependencies
├── README.md            # This file
└── templates/
    └── index.html       # Main web interface
```

### Configuration

All settings are hardcoded in `app.py` for maximum simplicity:

- **API Key**: Included in the code
- **Model**: claude-opus-4-20250514
- **Max tokens**: 8000 (optimized for performance)
- **Temperature**: 0.3 (optimized for accuracy)
- **Streaming**: Enabled for longer operations
- **Host**: 0.0.0.0
- **Port**: 5000
- **Max code length**: 10000 characters
- **Max error length**: 2000 characters

## Troubleshooting

### Common Issues

1. **"Network error" message**
   - Check your internet connection
   - Verify the Claude API service is available

2. **Application won't start**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check that Python 3.7+ is being used

3. **Port already in use**
   - Close other applications using port 5000
   - Or modify the `FLASK_PORT` in `app.py`

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve this tool!

## License

This project is open source and available under the MIT License.

## Support

If you encounter any issues or need help:

1. Check the troubleshooting section above
2. Ensure your API key is valid and has credits
3. Verify all dependencies are installed correctly
4. Check the console for detailed error messages

---

**Happy debugging!** 🐛➡️✅ 