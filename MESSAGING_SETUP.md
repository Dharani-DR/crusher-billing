# SMS & WhatsApp Integration Setup Guide

## Overview
The billing system now supports SMS and WhatsApp notifications via multiple providers:
- **Twilio** (SMS & WhatsApp)
- **MSG91** (SMS)
- **Generic HTTP API** (SMS & WhatsApp)

## Setup Instructions

### 1. Install Dependencies
```bash
pip install twilio requests
```

### 2. Configure Messaging Settings

Go to **Admin Panel → Messaging Settings** and configure:

#### For Twilio (SMS & WhatsApp):
1. **SMS Provider**: Select "Twilio"
2. **SMS API Key**: Your Twilio Account SID
3. **SMS API Secret**: Your Twilio Auth Token
4. **SMS Sender ID**: Your Twilio phone number (e.g., +1234567890)
5. **WhatsApp Provider**: Select "Twilio"
6. **WhatsApp Sender Number**: Your Twilio WhatsApp number (format: whatsapp:+1234567890)

#### For MSG91 (SMS only):
1. **SMS Provider**: Select "MSG91"
2. **SMS API Key**: Your MSG91 Auth Key
3. **SMS Sender ID**: Your MSG91 Sender ID (6 characters)

#### For Generic HTTP API:
1. **SMS Provider**: Select "Generic HTTP API"
2. **SMS API Key**: Your API key
3. **SMS API URL**: Your API endpoint URL
4. **SMS Sender ID**: Your sender ID

### 3. Configure Templates

#### SMS Template Variables:
- `{customer}` - Customer name
- `{amount}` - Invoice amount
- `{bill_no}` - Bill number
- `{date}` - Invoice date
- `{pdf_link}` - Link to download PDF

Example:
```
Dear {customer}, Your bill {bill_no} for ₹{amount} is ready. Date: {date}. Download: {pdf_link}
```

#### WhatsApp Template Variables:
Same as SMS template variables.

### 4. Enable Auto-Send

Check the boxes:
- ✅ **Auto-send SMS after invoice creation**
- ✅ **Auto-send WhatsApp after invoice creation**

### 5. Test Integration

1. Enter a test phone number in the test field
2. Click **"Send Test SMS"** or **"Send Test WhatsApp"**
3. Verify you receive the test message

## Twilio Setup (Recommended)

### Step 1: Create Twilio Account
1. Go to https://www.twilio.com
2. Sign up for a free account
3. Get your Account SID and Auth Token from the dashboard

### Step 2: Get a Phone Number
1. In Twilio Console, go to Phone Numbers → Buy a Number
2. Select a number with SMS capabilities
3. For WhatsApp, you need to use Twilio's WhatsApp Sandbox (free) or get approved for production

### Step 3: WhatsApp Sandbox Setup (Free Testing)
1. Go to Twilio Console → Messaging → Try it out → Send a WhatsApp message
2. Follow instructions to join the sandbox
3. Use the sandbox number format: `whatsapp:+14155238886`

### Step 4: Configure in Admin Panel
- SMS API Key: Your Account SID
- SMS API Secret: Your Auth Token
- SMS Sender ID: Your Twilio phone number (+1234567890)
- WhatsApp Sender Number: `whatsapp:+14155238886` (sandbox) or your production number

## MSG91 Setup (India)

### Step 1: Create MSG91 Account
1. Go to https://msg91.com
2. Sign up and verify your account
3. Get your Auth Key from the dashboard

### Step 2: Get Sender ID
1. Apply for a 6-character sender ID
2. Wait for approval (usually 24-48 hours)

### Step 3: Configure in Admin Panel
- SMS Provider: MSG91
- SMS API Key: Your Auth Key
- SMS Sender ID: Your approved sender ID

## Troubleshooting

### SMS Not Sending
1. Check API credentials are correct
2. Verify phone number format (+91XXXXXXXXXX)
3. Check account balance (Twilio/MSG91)
4. Review error messages in flash notifications

### WhatsApp Not Sending
1. For Twilio: Ensure you're using the correct WhatsApp number format
2. Verify the recipient has joined the WhatsApp sandbox (if using sandbox)
3. Check Twilio console for delivery status

### Template Variables Not Working
- Ensure variables are wrapped in curly braces: `{customer}`
- Check spelling matches exactly
- Verify template is saved correctly

## API Rate Limits

- **Twilio**: Varies by account type (free tier: limited)
- **MSG91**: Varies by plan
- **Generic API**: Depends on provider

## Security Notes

- Never commit API keys to version control
- Use environment variables for production
- Regularly rotate API keys
- Monitor usage to prevent abuse

## Support

For provider-specific issues:
- **Twilio**: https://support.twilio.com
- **MSG91**: https://help.msg91.com

