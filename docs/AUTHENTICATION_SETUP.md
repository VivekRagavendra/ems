# Authentication Setup Guide

This guide explains how to set up AWS Cognito authentication for the EKS Application Controller dashboard.

## Overview

The dashboard now requires users to authenticate via AWS Cognito before accessing the API. This provides:

- ✅ Secure access control
- ✅ User management via AWS Cognito
- ✅ JWT token-based authentication
- ✅ Session management

## Prerequisites

1. Cognito User Pool and Client already deployed (via Terraform)
2. AWS CLI configured with appropriate permissions
3. Access to update Cognito configuration

## Setup Steps

### Step 1: Get Cognito Configuration Values

Run the helper script to automatically fetch and update your config:

```bash
cd /Users/viveks/EMS
export CONFIG_NAME=config.demo.yaml
bash scripts/get-cognito-config.sh
```

This will:
- Find your Cognito User Pool
- Get the Client ID
- Update `config/config.demo.yaml` with the values

### Step 2: Update Cognito Callback URLs

The Cognito client needs to know which URLs are allowed for redirects after login.

**Get your S3 bucket website URL:**
```bash
# From config.demo.yaml
S3_BUCKET=$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['s3']['ui_bucket_name'])")
REGION=$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['aws']['region'])")
echo "S3 Website URL: http://${S3_BUCKET}.s3-website-${REGION}.amazonaws.com"
```

**Update Cognito callback URLs:**
```bash
# Get User Pool ID and Client ID from config
POOL_ID=$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['cognito']['user_pool_id'])")
CLIENT_ID=$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['cognito']['client_id'])")
S3_URL="http://$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['s3']['ui_bucket_name'])").s3-website-$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['aws']['region'])").amazonaws.com"

# Update callback URLs
aws cognito-idp update-user-pool-client \
  --user-pool-id "$POOL_ID" \
  --client-id "$CLIENT_ID" \
  --region us-east-1 \
  --callback-urls "http://localhost:5173" "$S3_URL" \
  --logout-urls "http://localhost:5173" "$S3_URL"
```

### Step 3: Deploy UI with Authentication

Deploy the UI with Cognito configuration:

```bash
export CONFIG_NAME=config.demo.yaml
bash scripts/deploy-ui.sh
```

This will:
- Build the React app with Cognito environment variables
- Deploy to S3
- Enable authentication in the UI

### Step 4: Create Test User

Create a test user in Cognito:

```bash
# Get User Pool ID
POOL_ID=$(python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c['cognito']['user_pool_id'])")

# Create user (replace email and password)
EMAIL="admin@example.com"
PASSWORD="TempPassword123!"

aws cognito-idp admin-create-user \
  --user-pool-id "$POOL_ID" \
  --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --temporary-password "$PASSWORD" \
  --region us-east-1

# Set permanent password (user will be prompted to change on first login)
aws cognito-idp admin-set-user-password \
  --user-pool-id "$POOL_ID" \
  --username "$EMAIL" \
  --password "$PASSWORD" \
  --permanent \
  --region us-east-1

echo "✅ User created: $EMAIL"
echo "   Password: $PASSWORD"
```

### Step 5: Deploy API Gateway Changes

Apply the API Gateway route changes to enable authentication:

```bash
cd infrastructure
export CONFIG_NAME=config.demo.yaml
terragrunt apply -target=aws_apigatewayv2_route.get_apps \
                  -target=aws_apigatewayv2_route.start_app \
                  -target=aws_apigatewayv2_route.stop_app \
                  -target=aws_apigatewayv2_route.db_start \
                  -target=aws_apigatewayv2_route.db_stop \
                  -target=aws_apigatewayv2_route.ec2_start \
                  -target=aws_apigatewayv2_route.ec2_stop \
                  -target=aws_apigatewayv2_route.get_app_cost \
                  -target=aws_apigatewayv2_route.get_app_schedule \
                  -target=aws_apigatewayv2_route.post_app_schedule \
                  -target=aws_apigatewayv2_route.post_app_schedule_enable
```

Or apply all changes:
```bash
terragrunt apply
```

## Testing Authentication

1. **Access the dashboard:**
   - Navigate to your S3 website URL
   - You should see a login page

2. **Login:**
   - Enter the email and password you created
   - Click "Sign In"
   - You should be redirected to the dashboard

3. **Verify API calls:**
   - Open browser DevTools (F12)
   - Check Network tab
   - API requests should include `Authorization: Bearer <token>` header

4. **Logout:**
   - Click the "Logout" button in the header
   - You should be redirected back to login

## Troubleshooting

### "Cognito not configured" warning

**Issue:** UI shows warning about Cognito not being configured.

**Solution:**
1. Verify `config/config.demo.yaml` has Cognito values:
   ```bash
   python3 -c "import yaml; f=open('config/config.demo.yaml'); c=yaml.safe_load(f); print(c.get('cognito', {}))"
   ```

2. Redeploy UI:
   ```bash
   bash scripts/deploy-ui.sh
   ```

### "401 Unauthorized" errors

**Issue:** API returns 401 Unauthorized.

**Solution:**
1. Check if user is logged in (check localStorage for `cognito_token`)
2. Verify token is being sent in requests (check Network tab)
3. Check if API Gateway routes have authorizer attached:
   ```bash
   aws apigatewayv2 get-route --api-id <api-id> --route-id <route-id> --region us-east-1
   ```

### Login page not showing

**Issue:** Dashboard loads without login page.

**Solution:**
1. Check if Cognito env vars are set in `.env.production`:
   ```bash
   cat ui/.env.production
   ```

2. Verify `VITE_COGNITO_USER_POOL_ID` and `VITE_COGNITO_CLIENT_ID` are present

3. Rebuild and redeploy:
   ```bash
   cd ui
   npm run build
   cd ..
   bash scripts/deploy-ui.sh
   ```

### Token expired errors

**Issue:** User gets logged out frequently.

**Solution:**
- Tokens expire after 1 hour by default
- The UI automatically refreshes tokens
- If issues persist, check Cognito token expiration settings

## Security Considerations

1. **HTTPS:** For production, use CloudFront with HTTPS instead of S3 website hosting
2. **Password Policy:** Cognito enforces strong passwords (configured in `infrastructure/cognito.tf`)
3. **MFA:** Consider enabling MFA for additional security
4. **User Management:** Use Cognito User Pool for user management, or integrate with your identity provider

## API Routes Requiring Authentication

All API routes now require authentication:

- `GET /apps` - List applications
- `POST /start` - Start application
- `POST /stop` - Stop application
- `POST /db/start` - Start database
- `POST /db/stop` - Stop database
- `POST /ec2/start` - Start EC2 instance
- `POST /ec2/stop` - Stop EC2 instance
- `GET /apps/{app}/cost` - Get cost data
- `GET /apps/{app}/schedule` - Get schedule
- `POST /apps/{app}/schedule` - Update schedule
- `POST /apps/{app}/schedule/enable` - Toggle schedule

**Public routes (no auth):**
- `GET /` - API information
- `GET /config/info` - Config information
- `OPTIONS /*` - CORS preflight

## Next Steps

1. ✅ Complete setup steps above
2. Create additional users as needed
3. Configure user groups/roles if needed
4. Set up CloudFront for HTTPS (recommended for production)
5. Configure MFA for enhanced security

## Support

For issues or questions:
1. Check browser console for errors
2. Check CloudWatch logs for API Handler Lambda
3. Verify Cognito configuration in AWS Console
4. Review this guide for troubleshooting steps
