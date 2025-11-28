# Authentication Setup Guide

## Overview

The EKS Application Controller now supports AWS Cognito authentication for secure access to the dashboard and API. This provides:

- ✅ User authentication (email/password)
- ✅ JWT token-based API authorization
- ✅ Session management
- ✅ Secure access control

## Architecture

```
┌─────────────────┐
│  React UI       │
│  (S3/CloudFront)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Cognito        │  ← User Authentication
│  User Pool      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  API Gateway    │  ← JWT Authorizer
│  + Authorizer   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Lambda         │
│  Functions      │
└─────────────────┘
```

## Deployment Steps

### Step 1: Deploy Infrastructure

Deploy the Cognito resources and updated API Gateway:

```bash
cd infrastructure
terragrunt apply
```

This creates:
- Cognito User Pool
- Cognito User Pool Client
- Cognito User Pool Domain
- API Gateway JWT Authorizer
- Updated API Gateway routes (with authentication)

### Step 2: Get Cognito Configuration

After deployment, get the Cognito configuration:

```bash
# Get User Pool ID
USER_POOL_ID=$(terragrunt output -raw cognito_user_pool_id)

# Get Client ID
CLIENT_ID=$(terragrunt output -raw cognito_client_id)

# Get Domain
DOMAIN=$(terragrunt output -raw cognito_domain)

echo "User Pool ID: $USER_POOL_ID"
echo "Client ID: $CLIENT_ID"
echo "Domain: $DOMAIN"
```

### Step 3: Create Initial User

Create the first user in Cognito:

```bash
# Option 1: Using AWS CLI
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username admin@example.com \
  --password "YourSecurePassword123!" \
  --permanent
```

**Or** use the AWS Console:
1. Go to AWS Console → Cognito → User Pools
2. Select your user pool
3. Go to "Users" tab
4. Click "Create user"
5. Enter email and temporary password
6. User will be prompted to change password on first login

### Step 4: Update Cognito Callback URLs

After deploying the UI, update the Cognito callback URLs:

```bash
# Get your S3 bucket URL (or CloudFront URL)
S3_URL="https://your-bucket-name.s3-website-us-east-1.amazonaws.com"

# Update callback URLs
aws cognito-idp update-user-pool-client \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --callback-urls "http://localhost:5173" "$S3_URL" \
  --logout-urls "http://localhost:5173" "$S3_URL"
```

### Step 5: Build and Deploy UI

Build the UI with Cognito configuration:

```bash
cd ui

# Install dependencies (including amazon-cognito-identity-js)
npm install

# Create .env.production with Cognito config
cat > .env.production << EOF
VITE_API_URL=$(cd ../infrastructure && terragrunt output -raw api_gateway_url)
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
EOF

# Build
npm run build

# Deploy to S3
S3_BUCKET=your-bucket-name
aws s3 sync dist/ s3://$S3_BUCKET/ --delete
```

### Step 6: Test Authentication

1. Open the dashboard URL
2. You should see the login screen
3. Enter your email and password
4. After successful login, you'll see the dashboard

## Configuration

### Environment Variables

The UI requires these environment variables (set during build):

- `VITE_API_URL`: API Gateway endpoint URL
- `VITE_COGNITO_USER_POOL_ID`: Cognito User Pool ID
- `VITE_COGNITO_CLIENT_ID`: Cognito User Pool Client ID

### Optional: Disable Authentication

If you want to temporarily disable authentication (for testing), simply don't set the Cognito environment variables. The UI will work without authentication, but the API Gateway will still require tokens.

To disable API Gateway authentication:
1. Comment out the `authorizer_id` and `authorization_type` in `infrastructure/api_gateway.tf`
2. Run `terragrunt apply`

## User Management

### Create Users

```bash
# Create user
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username user@example.com \
  --user-attributes Name=email,Value=user@example.com \
  --temporary-password "TempPass123!"

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username user@example.com \
  --password "SecurePassword123!" \
  --permanent
```

### List Users

```bash
aws cognito-idp list-users \
  --user-pool-id $USER_POOL_ID
```

### Delete User

```bash
aws cognito-idp admin-delete-user \
  --user-pool-id $USER_POOL_ID \
  --username user@example.com
```

### Reset Password

```bash
aws cognito-idp admin-reset-user-password \
  --user-pool-id $USER_POOL_ID \
  --username user@example.com \
  --no-verify-email
```

## Security Features

### Password Policy

The Cognito User Pool enforces:
- Minimum 8 characters
- Requires uppercase letter
- Requires lowercase letter
- Requires number
- Requires symbol

### Session Management

- Tokens are stored in localStorage
- Tokens are automatically refreshed when expired
- Users are logged out if token refresh fails

### API Authorization

- All API calls include `Authorization: Bearer <token>` header
- API Gateway validates JWT tokens
- Invalid/expired tokens result in 401 Unauthorized

## Troubleshooting

### "Cognito not configured" Warning

**Issue**: UI shows warning about missing Cognito configuration.

**Solution**: Ensure environment variables are set during build:
```bash
VITE_COGNITO_USER_POOL_ID=... VITE_COGNITO_CLIENT_ID=... npm run build
```

### "401 Unauthorized" Error

**Issue**: API calls fail with 401.

**Solutions**:
1. Check if token is expired - try logging out and back in
2. Verify API Gateway authorizer is configured correctly
3. Check Cognito User Pool and Client IDs match

### Login Fails

**Issue**: Cannot log in with valid credentials.

**Solutions**:
1. Verify user exists in Cognito User Pool
2. Check if user is confirmed (email verified)
3. Verify password is correct
4. Check browser console for errors

### Callback URL Mismatch

**Issue**: Login redirect fails.

**Solution**: Update Cognito callback URLs to match your dashboard URL:
```bash
aws cognito-idp update-user-pool-client \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --callback-urls "https://your-dashboard-url.com"
```

## Cost

- **Cognito**: $0.0055 per MAU (Monthly Active User)
- **First 50,000 MAU**: Free
- **Estimated cost**: $0-5/month for <100 users

## Next Steps

After authentication is working:

1. **Add MFA** (optional): Enable MFA in Cognito User Pool settings
2. **Custom Domain** (optional): Use your own domain for Cognito hosted UI
3. **User Groups** (optional): Create user groups for role-based access
4. **Password Reset**: Enable self-service password reset

## References

- [AWS Cognito Documentation](https://docs.aws.amazon.com/cognito/)
- [amazon-cognito-identity-js](https://github.com/amazon-archives/amazon-cognito-identity-js)
- [API Gateway JWT Authorizer](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)

