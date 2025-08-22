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

## 📊 Analytics System

### Overview
The application includes a comprehensive analytics system that tracks:
- **Pageviews**: Every page visit and SPA navigation
- **Unique Visitors**: Anonymous session-based tracking (no PII)
- **Chat Questions**: Count of AI assistant interactions
- **Geographic Data**: Visitor locations displayed on a heat map
- **Daily Metrics**: Time-series data for trends

### Database Setup
The analytics system uses PostgreSQL for data persistence:

1. **For Render Deployment**: The `render.yaml` file automatically provisions a PostgreSQL database
2. **For Local Development**: Set `DATABASE_URL` in your environment:
   ```bash
   export DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
   ```

### Environment Variables
Required for analytics functionality:
```bash
DATABASE_URL=postgresql://user:password@host:port/database
SECRET_KEY=your-secret-key-for-sessions
ADMIN_TOKEN=your-admin-token-for-dashboard-access
```

### Analytics Dashboard
Access the analytics dashboard at `/admin/analytics?token=YOUR_ADMIN_TOKEN`

**Features:**
- **Real-time Statistics**: Total pageviews, unique visitors, chat questions
- **Daily Breakdown**: Day-by-day metrics for the last 30 days
- **Top Pages**: Most visited pages on your site
- **Top Referrers**: Sources of incoming traffic
- **Geographic Heat Map**: US states heat map showing visitor distribution

### API Endpoints

#### Collect Events
```http
POST /api/analytics/event
Content-Type: application/json

{
  "type": "pageview" | "chat_question",
  "path": "/current-page",
  "ref": "https://referrer.com/",
  "meta": {"custom": "data"}
}
```

#### Get Statistics
```http
GET /api/analytics/stats?days=30
```

Returns comprehensive analytics data including totals, daily breakdown, top pages, and referrers.

### Client-Side Tracking
The analytics system automatically tracks:
- **Page Loads**: Initial page visits
- **SPA Navigation**: Single-page app route changes
- **Chat Interactions**: When users submit questions

**Manual Tracking:**
```javascript
// Track custom pageview
window.analyticsTrack('/custom-page', {custom: 'metadata'});

// Track chat interaction
window.analyticsChatHit({prompt_length: 50});
```

### Privacy & Security
- **No PII**: Only anonymous session IDs, no personal information
- **IP Privacy**: IP addresses stored for geolocation only
- **Secure Cookies**: HttpOnly, Secure, SameSite=Lax
- **Strict CSP**: Content Security Policy without unsafe-eval
- **Rate Limiting**: Built-in protection against abuse

### Data Retention
- Events are stored indefinitely by default
- Consider implementing data retention policies for production
- Geographic data is aggregated at the state level (US) or country level (international)

### Troubleshooting

**Database Connection Issues:**
```bash
# Check if DATABASE_URL is set
echo $DATABASE_URL

# Verify database connectivity
python -c "from db import engine; print('✅ Database connected' if engine else '❌ No connection')"
```

**Missing Analytics Data:**
1. Verify `DATABASE_URL` is properly configured
2. Check that `/static/analytics.js` is being served
3. Ensure `ADMIN_TOKEN` is set for dashboard access
4. Check browser console for JavaScript errors

**Performance Optimization:**
- Analytics events are collected asynchronously
- Database queries use indexes for optimal performance
- Failed analytics calls don't impact site functionality

## 🔧 Render Blueprint Secrets

### Why ADMIN_TOKEN Was Empty

The Blueprint previously used `env: python` (wrong key). When a variable is defined via Blueprint with `generateValue: true`, Render generates it only if a value doesn't already exist. If `ADMIN_TOKEN` was created in the dashboard (even empty), generation is skipped and you end up with an empty runtime variable.

### Fix Steps to Follow on Render After This Commit

1. **Go to the service `veterans-benefits-ai` → Environment tab**

2. **If `ADMIN_TOKEN` exists (especially if blank), delete that row completely** (don't leave an empty value)

3. **In Blueprints, click Sync / Apply** so the updated render.yaml is applied to the existing service

4. **Redeploy the service**

5. **In the service Shell, verify:**
   ```bash
   printenv | grep '^TEST_FLAG='        # expect: TEST_FLAG=on
   printenv | grep '^ADMIN_TOKEN='      # line should exist
   printf %s "$ADMIN_TOKEN" | wc -c     # should be > 0
   ```

### Alternative: Manual Service Setup

If the service was created manually (not from Blueprint):

- **Either** recreate from the Blueprint, **or**
- **Manually set `ADMIN_TOKEN`** as a secret in the Environment tab (give it any strong value); in that case, `generateValue: true` isn't used

### About sync: false Keys

`PINECONE_API_KEY` and `OPENAI_API_KEY` won't be auto-populated from the Blueprint. Ensure they're set in the Render dashboard for the live service.

### Token Length Verification

Use the provided script to safely verify token generation without exposing secrets:

```bash
# In Render shell
./scripts/verify_admin_token_len.sh
# Should output a positive integer (typically 32+ characters)
```
