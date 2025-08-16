<<<<<<< HEAD
# Veterans Benefits Knowledge Base Assistant

A Flask-based web application that provides an AI-powered assistant for veterans benefits questions using Pinecone's vector database and assistant capabilities.

## 🚀 Features

- **AI-Powered Q&A**: Ask questions about veterans benefits and get intelligent responses
- **Citation Tracking**: View source documents and page references for all answers
- **Modern UI**: Clean, responsive web interface
- **Real-time Processing**: Instant responses with loading states

## 📁 Project Structure

```
Vb_/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── env.txt               # Environment variables (rename to .env)
├── templates/
│   └── index.html        # Main web interface
├── static/               # CSS, JS, images (if needed)
└── README.md            # This file
```

## 🛠️ Setup Instructions

### 1. Install Python Dependencies

```bash
# Navigate to project directory
cd Vb_

# Install required packages
pip install -r requirements.txt
```

### 2. Environment Configuration

1. Rename `env.txt` to `.env` (or create a new `.env` file)
2. Update the following variables:

```env
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ASSISTANT_NAME=your_assistant_name_here
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
```

### 3. Run the Application

```bash
# Start the Flask server
python app.py
```

The application will be available at: `http://localhost:5000`

## 🔧 Configuration

### Pinecone Setup
- Ensure you have a Pinecone account and API key
- Create an assistant in your Pinecone console
- Update the `PINECONE_ASSISTANT_NAME` in your environment variables

### Firecrawl Integration
- The application is configured to work with Firecrawl MCP
- Ensure your Firecrawl API key is set in the environment variables

## 📱 Usage

1. Open your web browser and navigate to `http://localhost:5000`
2. Type your veterans benefits question in the text area
3. Click "Ask Question" or press Ctrl+Enter
4. View the AI-generated response with source citations

## 🚨 Troubleshooting

### Common Issues

1. **"Pinecone assistant not available"**
   - Check your Pinecone API key
   - Verify the assistant name is correct
   - Ensure your Pinecone account is active

2. **Import errors**
   - Run `pip install -r requirements.txt`
   - Check Python version compatibility

3. **Environment variables not loading**
   - Ensure `.env` file is in the project root
   - Check variable names match exactly

### Health Check

Visit `/health` endpoint to check application status:
```bash
curl http://localhost:5000/health
```

## 🔒 Security Notes

- Never commit API keys to version control
- Use environment variables for sensitive data
- Consider using a `.gitignore` file to exclude `.env`

## 📈 Future Enhancements

- User authentication
- Question history
- Export functionality
- Advanced search filters
- Mobile app version

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is for educational and informational purposes related to veterans benefits assistance.

## 🆘 Support

For technical support or questions about veterans benefits:
- Technical issues: Check the troubleshooting section
- Veterans benefits questions: Use the application interface
- General support: Contact your local VA office








=======
# Veterans Benefits Knowledge Base Assistant

A Flask-based web application that provides an AI-powered assistant for veterans benefits questions using Pinecone's vector database and assistant capabilities.

## 🚀 Features

- **AI-Powered Q&A**: Ask questions about veterans benefits and get intelligent responses
- **Citation Tracking**: View source documents and page references for all answers
- **Modern UI**: Clean, responsive web interface
- **Real-time Processing**: Instant responses with loading states

## 📁 Project Structure

```
Vb_/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── env.txt               # Environment variables (rename to .env)
├── templates/
│   └── index.html        # Main web interface
├── static/               # CSS, JS, images (if needed)
└── README.md            # This file
```

## 🛠️ Setup Instructions

### 1. Install Python Dependencies

```bash
# Navigate to project directory
cd Vb_

# Install required packages
pip install -r requirements.txt
```

### 2. Environment Configuration

1. Rename `env.txt` to `.env` (or create a new `.env` file)
2. Update the following variables:

```env
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ASSISTANT_NAME=your_assistant_name_here
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
```

### 3. Run the Application

```bash
# Start the Flask server
python app.py
```

The application will be available at: `http://localhost:5000`

## 🔧 Configuration

### Pinecone Setup
- Ensure you have a Pinecone account and API key
- Create an assistant in your Pinecone console
- Update the `PINECONE_ASSISTANT_NAME` in your environment variables

### Firecrawl Integration
- The application is configured to work with Firecrawl MCP
- Ensure your Firecrawl API key is set in the environment variables

## 📱 Usage

1. Open your web browser and navigate to `http://localhost:5000`
2. Type your veterans benefits question in the text area
3. Click "Ask Question" or press Ctrl+Enter
4. View the AI-generated response with source citations

## 🚨 Troubleshooting

### Common Issues

1. **"Pinecone assistant not available"**
   - Check your Pinecone API key
   - Verify the assistant name is correct
   - Ensure your Pinecone account is active

2. **Import errors**
   - Run `pip install -r requirements.txt`
   - Check Python version compatibility

3. **Environment variables not loading**
   - Ensure `.env` file is in the project root
   - Check variable names match exactly

### Health Check

Visit `/health` endpoint to check application status:
```bash
curl http://localhost:5000/health
```

## 🔒 Security Notes

- Never commit API keys to version control
- Use environment variables for sensitive data
- Consider using a `.gitignore` file to exclude `.env`

## 📈 Future Enhancements

- User authentication
- Question history
- Export functionality
- Advanced search filters
- Mobile app version

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is for educational and informational purposes related to veterans benefits assistance.

## 🆘 Support

For technical support or questions about veterans benefits:
- Technical issues: Check the troubleshooting section
- Veterans benefits questions: Use the application interface
- General support: Contact your local VA office








>>>>>>> b6374a9 (Add new features and fix bugs)
