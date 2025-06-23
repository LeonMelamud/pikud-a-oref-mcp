#!/bin/bash

echo "🚀 Installing Pikud Haoref VS Code Extension"

# Install VSCE if not installed
if ! command -v vsce &> /dev/null; then
    echo "📦 Installing vsce (VS Code Extension Manager)..."
    npm install -g vsce
fi

# Compile the extension
echo "🔨 Compiling extension..."
npm run compile

# Package the extension
echo "📦 Packaging extension..."
vsce package

# Install the extension
echo "🔧 Installing extension in VS Code..."
VSIX_FILE=$(ls *.vsix | head -1)
if [ -f "$VSIX_FILE" ]; then
    code --install-extension "$VSIX_FILE"
    echo "✅ Extension installed successfully!"
    echo ""
    echo "🎯 Next steps:"
    echo "1. Restart VS Code"
    echo "2. Look for '🚨 Emergency Alerts' in the Explorer sidebar"
    echo "3. Use Cmd+Shift+P → 'Pikud Haoref: Start Alert Monitoring'"
    echo "4. Test with: make test-alert"
else
    echo "❌ Failed to create .vsix package"
    exit 1
fi