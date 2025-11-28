# Next Steps After Multi-Account Refactoring

## ✅ What's Been Completed

- ✅ Single configuration file (`config/config.yaml`) created
- ✅ All Lambda functions updated to read from config
- ✅ Terraform/Terragrunt updated to use config
- ✅ Deployment scripts updated
- ✅ UI updated to load from config
- ✅ Documentation updated

## 🎯 Immediate Next Steps

### 1. Verify Configuration (5 minutes)

Test that your config file is valid and can be loaded:

```bash
# Install PyYAML if not already installed
pip3 install PyYAML

# Test config loading
python3 scripts/load-config.py

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

### 2. Review Your Configuration (10 minutes)

Open `config/config.yaml` and verify all values are correct:

- ✅ AWS account ID
- ✅ AWS region
- ✅ EKS cluster name
- ✅ DynamoDB table name
- ✅ S3 bucket name
- ✅ Application namespace mappings
- ✅ NodeGroup defaults
- ✅ EC2 tag keys

**Important**: Make sure all application hostnames and namespaces match your actual EKS cluster!

### 3. Test Lambda Config Loading (Optional - 15 minutes)

If you want to test locally before deploying:

```bash
# Test config loader module
python3 -c "
import sys
sys.path.insert(0, 'lambdas/api-handler')
from config.loader import get_eks_cluster_name, get_dynamodb_table_name
print('EKS Cluster:', get_eks_cluster_name())
print('DynamoDB Table:', get_dynamodb_table_name())
"
```

### 4. Rebuild Lambda Packages (5 minutes)

Rebuild Lambda packages with the new config system:

```bash
./build-lambdas.sh
```

This will:
- Install dependencies (including PyYAML)
- Copy config directory to each Lambda package
- Create deployment ZIP files

**Verify**: Check that `build/*.zip` files are created and contain the config directory.

### 5. Deploy Infrastructure (10-15 minutes)

Deploy/update infrastructure with new config:

```bash
cd infrastructure

# Preview changes
terragrunt plan

# Apply changes (if plan looks good)
terragrunt apply
```

**Note**: Terragrunt will automatically read from `config/config.yaml` via `scripts/load-config.py`.

### 6. Update Lambda Functions (5 minutes)

Deploy updated Lambda functions:

```bash
# For each Lambda function
aws lambda update-function-code \
  --function-name eks-app-controller-api-handler \
  --zip-file fileb://build/api-handler.zip \
  --region us-east-1

aws lambda update-function-code \
  --function-name eks-app-controller-controller \
  --zip-file fileb://build/controller.zip \
  --region us-east-1

aws lambda update-function-code \
  --function-name eks-app-controller-discovery \
  --zip-file fileb://build/discovery.zip \
  --region us-east-1

aws lambda update-function-code \
  --function-name eks-app-controller-health-monitor \
  --zip-file fileb://build/health-monitor.zip \
  --region us-east-1
```

### 7. Verify Lambda Functions (5 minutes)

Check CloudWatch logs to ensure config is loading correctly:

```bash
# Check API Handler logs
aws logs tail /aws/lambda/eks-app-controller-api-handler --follow --since 5m

# Look for:
# ✅ No "Could not load config.yaml" warnings
# ✅ Config values being used correctly
```

### 8. Deploy UI (5 minutes)

Deploy UI with config-based API URL:

```bash
# Get API Gateway URL first (if not already in config.yaml)
API_GATEWAY_URL=$(aws apigatewayv2 get-apis --query 'Items[?Name==`eks-app-controller-api`].ApiEndpoint' --output text)

# Update config.yaml with API URL (or set environment variable)
# Then deploy:
./scripts/deploy-ui.sh
```

The script will:
- Read S3 bucket from config.yaml
- Read/generate API URL
- Build UI with correct API endpoint
- Deploy to S3

### 9. Test the System (10 minutes)

1. **Open the dashboard** in your browser
2. **Check application status** - should load correctly
3. **Test start/stop** - verify operations work
4. **Check logs** - ensure no config-related errors

### 10. Update API URL in Config (If Needed)

After deployment, if API Gateway URL changed:

1. Get the new URL:
   ```bash
   aws apigatewayv2 get-apis --query 'Items[?Name==`eks-app-controller-api`].ApiEndpoint' --output text
   ```

2. Update `config/config.yaml`:
   ```yaml
   ui:
     api_url: "https://YOUR_NEW_API_URL.execute-api.us-east-1.amazonaws.com"
   ```

3. Redeploy UI:
   ```bash
   ./scripts/deploy-ui.sh
   ```

## 🔍 Verification Checklist

After deployment, verify:

- [ ] Config file loads without errors
- [ ] Lambda functions can import config module
- [ ] Terraform reads config values correctly
- [ ] UI loads API URL from config.json
- [ ] Dashboard shows applications correctly
- [ ] Start/stop operations work
- [ ] No config-related errors in CloudWatch logs

## 🚨 Troubleshooting

### Config file not found in Lambda

**Symptom**: `⚠️ Warning: Could not load config.yaml`

**Solution**:
1. Verify `build-lambdas.sh` copies config directory
2. Check Lambda package contains `config/` directory
3. Verify `config/config.yaml` exists in package

### Terraform can't read config

**Symptom**: Terragrunt fails with config loading error

**Solution**:
1. Install PyYAML: `pip3 install PyYAML`
2. Test script: `python3 scripts/load-config.py`
3. Check Python 3 is available: `python3 --version`

### UI shows wrong API URL

**Symptom**: Dashboard can't connect to API

**Solution**:
1. Check `config/config.yaml` has correct `ui.api_url`
2. Verify `config.json` is generated during build
3. Check browser console for API URL
4. Redeploy UI: `./scripts/deploy-ui.sh`

## 📚 Additional Resources

- [Configuration Guide](docs/CONFIGURATION.md) - Complete config reference
- [Multi-Account Refactor Summary](MULTI_ACCOUNT_REFACTOR.md) - What changed
- [README](README.md) - Main documentation
- [Quick Start](QUICKSTART.md) - Quick deployment guide

## 🎉 Success Criteria

You're done when:

1. ✅ All Lambda functions load config without errors
2. ✅ Dashboard loads and shows applications
3. ✅ Start/stop operations work correctly
4. ✅ No hard-coded values remain (all from config.yaml)
5. ✅ Can deploy to new account by only changing config.yaml

## 💡 Pro Tips

1. **Keep config.yaml private** - It contains account-specific values
2. **Use config.example.yaml** - Share this with your team
3. **Version control config separately** - Consider using AWS Secrets Manager or Parameter Store
4. **Test in dev first** - Always test config changes in dev before production
5. **Document custom mappings** - Keep notes on why certain mappings exist

---

**Ready to deploy?** Start with step 1 and work through the checklist! 🚀

