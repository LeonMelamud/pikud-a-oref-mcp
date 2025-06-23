import * as vscode from 'vscode';
import * as http from 'http';

const EventSource = require('eventsource');

interface Alert {
    id: string;
    type: string;
    cities: string[];
    instructions: string;
    received_at: string;
}

class AlertProvider implements vscode.TreeDataProvider<AlertItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<AlertItem | undefined | null | void> = new vscode.EventEmitter<AlertItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<AlertItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private alerts: Alert[] = [];
    private eventSource: any = null;
    private isConnected: boolean = false;

    constructor() {
        this.startListening();
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: AlertItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: AlertItem): Thenable<AlertItem[]> {
        if (!element) {
            // Root level - show connection status and alerts
            const items: AlertItem[] = [];
            
            // Connection status
            const statusItem = new AlertItem(
                this.isConnected ? '🟢 Connected to Alert Stream' : '🔴 Disconnected',
                vscode.TreeItemCollapsibleState.None
            );
            statusItem.tooltip = this.isConnected ? 'Receiving real-time alerts' : 'Not connected to alert stream';
            items.push(statusItem);

            // Recent alerts
            if (this.alerts.length === 0) {
                items.push(new AlertItem('📭 No alerts received', vscode.TreeItemCollapsibleState.None));
            } else {
                this.alerts.forEach((alert, index) => {
                    const alertItem = new AlertItem(
                        `🚨 ${alert.type}`,
                        vscode.TreeItemCollapsibleState.Collapsed
                    );
                    alertItem.id = `${alert.id}-${new Date(alert.received_at).getTime()}-${index}`; // More unique ID
                    alertItem.alert = alert;
                    alertItem.contextValue = 'alertItem'; // Set context value to show commands
                    alertItem.tooltip = `Areas: ${alert.cities.join(', ')}\nTime: ${new Date(alert.received_at).toLocaleString()}`;
                    items.push(alertItem);
                });
            }

            return Promise.resolve(items);
        } else if (element.alert) {
            // Show alert details
            const alert = element.alert;
            return Promise.resolve([
                new AlertItem(`📍 Areas: ${alert.cities.join(', ')}`, vscode.TreeItemCollapsibleState.None),
                new AlertItem(`⚠️ Type: ${alert.type}`, vscode.TreeItemCollapsibleState.None),
                new AlertItem(`📋 Instructions: ${alert.instructions}`, vscode.TreeItemCollapsibleState.None),
                new AlertItem(`🕐 Time: ${new Date(alert.received_at).toLocaleString()}`, vscode.TreeItemCollapsibleState.None)
            ]);
        }

        return Promise.resolve([]);
    }

    startListening() {
        const config = vscode.workspace.getConfiguration('pikudHaoref');
        const apiUrl = config.get<string>('apiUrl', 'http://localhost:8002/api/alerts-stream');
        const apiKey = config.get<string>('apiKey', 'poha-test-key-2024-secure');
        const enableNotifications = config.get<boolean>('enableNotifications', true);

        if (this.eventSource) {
            this.eventSource.close();
        }

        try {
            this.eventSource = new EventSource(apiUrl, {
                headers: {
                    'X-API-Key': apiKey
                }
            });

            this.eventSource.onopen = () => {
                this.isConnected = true;
                this.refresh();
                vscode.window.showInformationMessage('🟢 Connected to Pikud Haoref alert stream');
            };

            this.eventSource.onmessage = (event: any) => {
                try {
                    // Ignore keep-alive messages and empty data
                    if (event.data === 'keep-alive' || !event.data) {
                        return;
                    }

                    const alertData = JSON.parse(event.data);

                    // Ignore non-alert messages which may not have an ID or city data
                    if (!alertData.id || (!alertData.cities && !alertData.data)) {
                        console.log("Ignoring non-alert message:", alertData);
                        return;
                    }

                    const alert: Alert = {
                        id: alertData.id,
                        type: alertData.title_en || alertData.type || 'Unknown Alert',
                        cities: alertData.cities || alertData.data || [],
                        instructions: alertData.instructions_en || alertData.instructions || alertData.title || 'No instructions provided',
                        received_at: new Date().toISOString()
                    };

                    // Add to beginning of array (most recent first)
                    this.alerts.unshift(alert);
                    
                    // Keep only last 50 alerts
                    if (this.alerts.length > 50) {
                        this.alerts = this.alerts.slice(0, 50);
                    }

                    this.refresh();

                    // Show notification if enabled
                    if (enableNotifications) {
                        const message = `🚨 EMERGENCY ALERT: ${alert.cities.join(', ')} - ${alert.type}`;
                        vscode.window.showWarningMessage(message, 'View Details').then(selection => {
                            if (selection === 'View Details') {
                                vscode.commands.executeCommand('workbench.view.explorer');
                            }
                        });
                    }

                    console.log('New alert received:', alert);
                } catch (error) {
                    console.error('Error parsing alert data:', error);
                }
            };

            this.eventSource.onerror = (error: any) => {
                this.isConnected = false;
                this.refresh();
                console.error('SSE connection error:', error);
                vscode.window.showErrorMessage('❌ Lost connection to alert stream. Attempting to reconnect...');
            };

        } catch (error) {
            vscode.window.showErrorMessage(`Failed to connect to alert stream: ${error}`);
        }
    }

    stopListening() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.refresh();
        vscode.window.showInformationMessage('🔴 Disconnected from alert stream');
    }

    deleteAlert(itemToDelete: AlertItem) {
        if (!itemToDelete.id) {
            return;
        }
        // Find the specific alert instance to delete using its unique tree item ID
        const index = this.alerts.findIndex((alert, idx) => {
            const item_id = `${alert.id}-${new Date(alert.received_at).getTime()}-${idx}`;
            // This is a bit of a hack, we should ideally store the unique ID on the alert object itself
            return itemToDelete.id?.startsWith(alert.id);
        });

        if (index !== -1) {
            this.alerts.splice(index, 1);
            this.refresh();
            vscode.window.showInformationMessage(`Alert cleared: ${itemToDelete.label}`);
        }
    }

    async sendTestAlert() {
        const config = vscode.workspace.getConfiguration('pikudHaoref');
        const apiKey = config.get<string>('apiKey', 'poha-test-key-2024-secure');
        
        const postData = JSON.stringify({
            data: ['VS Code Extension Test'],
            cat: '1',
            language: 'en'
        });

        const options = {
            hostname: 'localhost',
            port: 8000,
            path: '/api/test/fake-alert',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey,
                'Content-Length': Buffer.byteLength(postData)
            }
        };

        return new Promise<void>((resolve, reject) => {
            const req = http.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => {
                    data += chunk;
                });
                res.on('end', () => {
                    if (res.statusCode === 200) {
                        try {
                            const result = JSON.parse(data);
                            vscode.window.showInformationMessage(`✅ Test alert sent: ${result.alert_id}`);
                            resolve();
                        } catch (error) {
                            vscode.window.showErrorMessage(`❌ Failed to parse response: ${error}`);
                            reject(error);
                        }
                    } else {
                        vscode.window.showErrorMessage(`❌ HTTP ${res.statusCode}`);
                        reject(new Error(`HTTP ${res.statusCode}`));
                    }
                });
            });

            req.on('error', (error) => {
                vscode.window.showErrorMessage(`❌ Failed to send test alert: ${error.message}`);
                reject(error);
            });

            req.write(postData);
            req.end();
        });
    }
}

class AlertItem extends vscode.TreeItem {
    alert?: Alert;

    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(label, collapsibleState);
    }
}

export function activate(context: vscode.ExtensionContext) {
    const alertProvider = new AlertProvider();
    
    // Register tree data provider
    vscode.window.registerTreeDataProvider('pikudHaorefAlerts', alertProvider);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('pikudHaoref.startAlerts', () => alertProvider.startListening()),
        vscode.commands.registerCommand('pikudHaoref.stopAlerts', () => alertProvider.stopListening()),
        vscode.commands.registerCommand('pikudHaoref.testAlert', () => alertProvider.sendTestAlert()),
        vscode.commands.registerCommand('pikudHaoref.deleteAlert', (item: AlertItem) => alertProvider.deleteAlert(item)),
        vscode.commands.registerCommand('pikudHaoref.installExtension', () => {
            vscode.window.showInformationMessage(
                '📦 To install this extension:\n\n1. Download the VSIX file: pikud-haoref-alerts-1.0.0.vsix\n2. Run: code --install-extension pikud-haoref-alerts-1.0.0.vsix\n3. Or use VS Code Extensions view > Install from VSIX',
                'Copy Install Command'
            ).then(selection => {
                if (selection === 'Copy Install Command') {
                    vscode.env.clipboard.writeText('code --install-extension /path/to/pikud-haoref-alerts-1.0.0.vsix');
                    vscode.window.showInformationMessage('📋 Command copied to clipboard');
                }
            });
        })
    );

    // Auto-start listening on activation
    alertProvider.startListening();

    vscode.window.showInformationMessage('🚨 Pikud Haoref Alert Monitor activated');
}

export function deactivate() {
    // This function is called when the extension is deactivated
}