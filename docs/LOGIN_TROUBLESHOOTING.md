# Login Troubleshooting Guide

## Quick Fixes

### 1. Clear Browser Cache
- **Windows/Linux**: Press `Ctrl + Shift + R` (hard refresh)
- **Mac**: Press `Cmd + Shift + R` (hard refresh)
- Or: Open DevTools (F12) > Application tab > Clear storage > Clear site data

### 2. Try Different Login Credentials

**Option 1: Username**
- Username: `demo-user`
- Password: `Demomaster@123`

**Option 2: Email**
- Email: `demo-user@example.com`
- Password: `Demomaster@123`

### 3. Check Browser Console

1. Open DevTools (F12)
2. Go to Console tab
3. Look for red error messages
4. Common errors:
   - `Cognito not configured` → UI needs rebuild (already done)
   - `UserNotFoundException` → Try using email instead of username
   - `NotAuthorizedException` → Wrong password or user not confirmed
   - `Network error` → CORS or API Gateway issue

### 4. Verify Cognito Configuration

Open browser console and type:
```javascript
// Check if Cognito is configured
console.log('Cognito Pool ID:', import.meta.env.VITE_COGNITO_USER_POOL_ID);
console.log('Cognito Client ID:', import.meta.env.VITE_COGNITO_CLIENT_ID);

// Check if token exists
localStorage.getItem('cognito_token');
```

## Common Issues

### Issue: "Cognito not configured" Warning

**Symptoms:**
- Dashboard shows warning about Cognito
- Login form doesn't appear

**Solution:**
1. Clear browser cache
2. Hard refresh the page
3. Check if `.env.production` has Cognito vars (already verified)

### Issue: Login Form Appears But Login Fails

**Symptoms:**
- Login form shows
- Entering credentials shows error
- Console shows authentication error

**Solutions:**
1. Try email instead of username: `demo-user@example.com`
2. Verify password is correct: `Demomaster@123`
3. Check console for specific error message
4. Verify user exists: Already confirmed ✅

### Issue: "UserNotFoundException"

**Solution:**
- User may need to be created (already done ✅)
- Try using email: `demo-user@example.com`

### Issue: "NotAuthorizedException"

**Solution:**
- Verify password: `Demomaster@123`
- User may need password reset
- Check if user is confirmed (already confirmed ✅)

### Issue: Network/CORS Errors

**Symptoms:**
- Console shows CORS errors
- Network tab shows failed requests

**Solution:**
- API Gateway CORS is configured ✅
- Check if API URL is correct
- Verify API Gateway routes have authorizer

### Issue: Token Not Being Sent

**Symptoms:**
- Login appears successful
- But API calls fail with 401

**Solution:**
1. Check Network tab
2. Look for `/apps` request
3. Verify `Authorization: Bearer <token>` header is present
4. If missing, login may have failed silently

## Step-by-Step Debugging

### Step 1: Verify UI Has Cognito Config

1. Open dashboard URL
2. Open DevTools (F12) > Console
3. Type: `localStorage.getItem('cognito_token')`
4. Should be `null` before login
5. After login, should have a long token string

### Step 2: Test Login Flow

1. Open DevTools (F12) > Network tab
2. Try to login
3. Look for:
   - Requests to Cognito (cognito-idp.amazonaws.com)
   - Requests to API Gateway (/apps endpoint)
   - Check if requests have Authorization header

### Step 3: Check for JavaScript Errors

1. Open DevTools (F12) > Console tab
2. Look for red error messages
3. Common errors:
   - `Cannot read property 'authenticateUser'` → Cognito library not loaded
   - `Cognito not configured` → Env vars not set
   - `Network request failed` → CORS or network issue

## Manual Testing

### Test Cognito Login Directly

1. Open browser console on dashboard page
2. Paste this code:

```javascript
// Test Cognito login
const { CognitoUserPool, CognitoUser, AuthenticationDetails } = window.AmazonCognitoIdentity || {};

const poolData = {
    UserPoolId: 'us-east-1_1I3UMxZM8',
    ClientId: '6brsnphuvtfn02td15a7sg47dd'
};

const userPool = new CognitoUserPool(poolData);
const cognitoUser = new CognitoUser({
    Username: 'demo-user',
    Pool: userPool
});

const authDetails = new AuthenticationDetails({
    Username: 'demo-user',
    Password: 'Demomaster@123'
});

cognitoUser.authenticateUser(authDetails, {
    onSuccess: (result) => {
        console.log('✅ Login successful!', result.getIdToken().getJwtToken().substring(0, 50));
    },
    onFailure: (err) => {
        console.error('❌ Login failed:', err);
    }
});
```

This will test if Cognito login works directly.

## Current Configuration

- **User Pool ID**: `us-east-1_1I3UMxZM8`
- **Client ID**: `6brsnphuvtfn02td15a7sg47dd`
- **Username**: `demo-user`
- **Email**: `demo-user@example.com`
- **Password**: `Demomaster@123`
- **User Status**: CONFIRMED ✅
- **SRP Auth**: Enabled ✅

## Still Not Working?

If login still doesn't work after trying all above:

1. **Share the exact error message** from browser console
2. **Share what happens** when you click "Sign In"
3. **Check Network tab** and share any failed requests
4. **Verify** you're using the correct dashboard URL

## Alternative: Test with Direct API Call

If UI login doesn't work, you can test if authentication works at all:

```bash
# Get token using AWS CLI
aws cognito-idp admin-initiate-auth \
  --user-pool-id us-east-1_1I3UMxZM8 \
  --client-id 6brsnphuvtfn02td15a7sg47dd \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=demo-user,PASSWORD=Demomaster@123 \
  --region us-east-1
```

Note: This uses ADMIN auth flow which may not be enabled. The UI uses SRP which should work.

