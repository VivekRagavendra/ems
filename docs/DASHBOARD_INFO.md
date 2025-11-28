# Dashboard Information

## ✅ Yes, the Codebase Includes a Dashboard!

The codebase **includes a complete React dashboard** in the `ui/` directory. However, it is **NOT automatically deployed** by the Terragrunt/OpenTofu infrastructure code.

## 📊 What the Dashboard Includes

The dashboard is a **modern, responsive React web application** that provides:

### Features:
- ✅ **Application List**: Automatically displays all discovered applications
- ✅ **Status Indicators**: 
  - 🟢 UP (green) - Application running
  - 🔴 DOWN (red) - Application stopped
  - 🟡 DEGRADED (yellow) - Partial functionality
- ✅ **One-Click Controls**: 
  - ▶ Start button - Starts entire application
  - ⏹ Stop button - Stops entire application
- ✅ **Application Details**: Shows hostnames, NodeGroups, PostgreSQL, Neo4j counts
- ✅ **Shared Resource Warnings**: Alerts when databases are shared
- ✅ **Auto-Refresh**: Updates every 30 seconds
- ✅ **Manual Refresh**: Refresh button to update immediately
- ✅ **Error Handling**: Shows clear error messages

### Dashboard Screenshot Description:

```
┌─────────────────────────────────────────────┐
│  EKS Application Controller    [🔄 Refresh]│
├─────────────────────────────────────────────┤
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ 🟢 mi.dev.mareana.com        [UP]    │   │
│  │ Hostnames: mi.dev.mareana.com        │   │
│  │ NodeGroups: 2                        │   │
│  │ PostgreSQL: 1                        │   │
│  │ Neo4j: 1                             │   │
│  │                                      │   │
│  │ [▶ Start]  [⏹ Stop]                 │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ 🔴 app2.example.com         [DOWN]   │   │
│  │ ...                                   │   │
│  │ [▶ Start]  [⏹ Stop]                 │   │
│  └──────────────────────────────────────┘   │
│                                              │
└─────────────────────────────────────────────┘
```

## 🚀 How to Deploy the Dashboard

The dashboard needs to be **manually deployed** after the infrastructure is created. Here's how:

### Step 1: Build the Dashboard

```bash
cd ui
npm install
npm run build
```

This creates a `dist/` directory with the compiled React app.

### Step 2: Deploy to S3

**Option A: Simple S3 Website Hosting**

```bash
# Create S3 bucket
aws s3 mb s3://eks-app-controller-ui

# Enable website hosting
aws s3 website s3://eks-app-controller-ui \
  --index-document index.html \
  --error-document index.html

# Get API Gateway URL
cd ../infrastructure
API_URL=$(terragrunt output -raw api_gateway_url)

# Deploy UI
cd ..
S3_BUCKET=eks-app-controller-ui API_URL=$API_URL ./scripts/deploy-ui.sh

# Get website URL
aws s3api get-bucket-website --bucket eks-app-controller-ui
# Access at: http://eks-app-controller-ui.s3-website-<region>.amazonaws.com
```

**Option B: S3 + CloudFront (Recommended for Production)**

```bash
# 1. Create S3 bucket
aws s3 mb s3://eks-app-controller-ui

# 2. Deploy UI to S3
cd infrastructure
API_URL=$(terragrunt output -raw api_gateway_url)
cd ..
S3_BUCKET=eks-app-controller-ui API_URL=$API_URL ./scripts/deploy-ui.sh

# 3. Create CloudFront distribution
aws cloudfront create-distribution \
  --origin-domain-name eks-app-controller-ui.s3.amazonaws.com \
  --default-root-object index.html

# 4. Access via CloudFront URL (HTTPS, global CDN)
```

### Step 3: Configure API URL

The dashboard needs to know the API Gateway URL. This is set during build:

```bash
# The deploy script automatically sets this
echo "VITE_API_URL=$API_URL" > ui/.env.production
npm run build
```

Or manually edit `ui/.env.production` before building.

## 📁 Dashboard Files

The dashboard consists of:

```
ui/
├── index.html          # HTML entry point
├── vite.config.js      # Build configuration
├── package.json        # Dependencies
└── src/
    ├── main.jsx        # React entry point
    ├── App.jsx         # Main dashboard component
    ├── App.css         # Dashboard styles
    └── index.css       # Global styles
```

## 🔧 Dashboard Configuration

### Environment Variables

The dashboard uses environment variables:

- `VITE_API_URL`: API Gateway endpoint URL
  - Set during build: `VITE_API_URL=https://... npm run build`
  - Or in `.env.production` file

### API Endpoints Used

The dashboard calls these API Gateway endpoints:

- `GET /apps` - List all applications
- `POST /start` - Start an application
- `POST /stop` - Stop an application

## 🎨 Dashboard Features in Detail

### 1. Application Cards

Each application is displayed as a card showing:
- Application name (hostname)
- Status badge with color coding
- Hostnames list
- Number of NodeGroups
- Number of PostgreSQL instances
- Number of Neo4j instances
- Shared resource warnings (if any)
- Start/Stop buttons

### 2. Status Colors

- **🟢 Green (UP)**: All components running
- **🔴 Red (DOWN)**: Application stopped or unreachable
- **🟡 Yellow (DEGRADED)**: Partial functionality (e.g., DB up but pods down)

### 3. Interactive Features

- **Refresh Button**: Manually refresh application list
- **Start Button**: 
  - Disabled when app is already UP
  - Shows "Starting..." during operation
  - Displays success/error alerts
- **Stop Button**:
  - Disabled when app is already DOWN
  - Shows "Stopping..." during operation
  - Warns about shared resources before stopping
  - Displays success/error alerts

### 4. Error Handling

- Shows error banner if API is unreachable
- Displays error messages for failed operations
- Handles network errors gracefully

## 🔐 Security Considerations

### Current State

- **Public Access**: Dashboard is publicly accessible (if deployed to S3/CloudFront)
- **No Authentication**: No login required
- **CORS**: API Gateway allows all origins

### Recommendations for Production

1. **Add Authentication**:
   - AWS Cognito for user authentication
   - API Keys for API Gateway
   - OAuth integration

2. **Restrict Access**:
   - CloudFront signed URLs
   - S3 bucket policies
   - VPC endpoints

3. **HTTPS Only**:
   - Use CloudFront with SSL certificate
   - Custom domain with ACM certificate

## 📊 Dashboard Access

After deployment, access the dashboard at:

- **S3 Website**: `http://eks-app-controller-ui.s3-website-<region>.amazonaws.com`
- **CloudFront**: `https://<distribution-id>.cloudfront.net`
- **Custom Domain**: `https://app-controller.yourdomain.com` (if configured)

## 🛠️ Development

To run the dashboard locally for development:

```bash
cd ui
npm install
npm run dev
```

Access at `http://localhost:5173` (Vite default port)

Set API URL in `.env.local`:
```
VITE_API_URL=https://your-api-gateway-url.execute-api.region.amazonaws.com
```

## 📝 Summary

| Question | Answer |
|----------|--------|
| **Does codebase include dashboard?** | ✅ Yes - Complete React dashboard |
| **Is it automatically deployed?** | ❌ No - Manual deployment required |
| **Where does it run?** | S3 (static hosting) or S3 + CloudFront |
| **What does it do?** | Lists apps, shows status, start/stop controls |
| **Is it production-ready?** | ✅ Yes, but add authentication for production |

## Next Steps

1. Deploy infrastructure with `terragrunt apply`
2. Get API Gateway URL: `terragrunt output api_gateway_url`
3. Deploy dashboard: `./scripts/deploy-ui.sh`
4. Access dashboard via S3 or CloudFront URL
5. (Optional) Add authentication and custom domain


