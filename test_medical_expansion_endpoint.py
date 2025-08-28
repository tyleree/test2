#!/usr/bin/env python3
"""
Simple Flask endpoint to demonstrate medical term expansion working.
"""

from flask import Flask, request, jsonify
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from medical_terms import expand_medical_query
    MEDICAL_EXPANSION_AVAILABLE = True
except ImportError:
    MEDICAL_EXPANSION_AVAILABLE = False
    def expand_medical_query(query):
        return query

app = Flask(__name__)

@app.route('/test-expansion', methods=['POST'])
def test_expansion():
    """Test endpoint to demonstrate medical term expansion."""
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({'error': 'No prompt provided'}), 400
        
        prompt = data['prompt']
        
        if MEDICAL_EXPANSION_AVAILABLE:
            expanded = expand_medical_query(prompt)
            expansion_applied = expanded != prompt
            
            return jsonify({
                'success': True,
                'medical_expansion_available': True,
                'original_query': prompt,
                'expanded_query': expanded,
                'expansion_applied': expansion_applied,
                'explanation': 'This demonstrates how medical terms are expanded to match VA documentation terminology.',
                'example_improvement': 'The query "ulnar neuropathy" expands to include "ulnar neuritis" and "ulnar nerve paralysis" which are the actual terms used in VA rating schedules.'
            })
        else:
            return jsonify({
                'success': False,
                'medical_expansion_available': False,
                'error': 'Medical expansion module not available'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': str(e.__class__.__name__)
        })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'medical_expansion_available': MEDICAL_EXPANSION_AVAILABLE,
        'message': 'Test server for medical term expansion is running'
    })

if __name__ == '__main__':
    print("🧪 Starting Medical Term Expansion Test Server...")
    print("📡 Available endpoints:")
    print("   GET  /health - Health check")
    print("   POST /test-expansion - Test medical term expansion")
    print("🚀 Server starting on http://localhost:5001")
    
    app.run(debug=True, port=5001)
