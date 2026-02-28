import * as vscode from 'vscode';

const EventSource = require('eventsource');

interface Alert {
    id: string;
    type: string;
    cities: string[];
    instructions: string;
    received_at: string;
}

// Map internal type codes to human-readable labels with icons
const ALERT_TYPE_LABELS: Record<string, { label: string; icon: string }> = {
    missiles:                    { label: 'Missile Threat',             icon: '🚀' },
    radiologicalEvent:           { label: 'Radiological Event',         icon: '☢️' },
    earthQuake:                  { label: 'Earthquake',                 icon: '🌍' },
    tsunami:                     { label: 'Tsunami',                    icon: '🌊' },
    hostileAircraftIntrusion:    { label: 'Hostile Aircraft Intrusion',  icon: '✈️' },
    hazardousMaterials:          { label: 'Hazardous Materials',        icon: '⚠️' },
    terroristInfiltration:       { label: 'Terrorist Infiltration',     icon: '🔫' },
    missilesDrill:               { label: 'Drill — Missile',            icon: '🔔' },
    earthQuakeDrill:             { label: 'Drill — Earthquake',         icon: '🔔' },
    radiologicalEventDrill:      { label: 'Drill — Radiological',       icon: '🔔' },
    tsunamiDrill:                { label: 'Drill — Tsunami',            icon: '🔔' },
    hostileAircraftIntrusionDrill:{ label: 'Drill — Aircraft',          icon: '🔔' },
    hazardousMaterialsDrill:     { label: 'Drill — Hazmat',             icon: '🔔' },
    terroristInfiltrationDrill:  { label: 'Drill — Infiltration',       icon: '🔔' },
    newsFlash:                   { label: 'News Flash',                 icon: '📰' },
    unknown:                     { label: 'Alert',                      icon: '🚨' },
};

function formatAlertLabel(alert: Alert): string {
    const info = ALERT_TYPE_LABELS[alert.type] || ALERT_TYPE_LABELS['unknown'];
    return `${info.icon} ${info.label}`;
}

function formatRelativeTime(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) { return 'just now'; }
    if (mins < 60) { return `${mins}m ago`; }
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) { return `${hrs}h ago`; }
    return new Date(iso).toLocaleDateString();
}

/** Tree item types to distinguish children in getChildren() */
type TreeNodeKind = 'status' | 'empty' | 'alert' | 'section' | 'city' | 'detail';

class AlertItem extends vscode.TreeItem {
    alert?: Alert;
    kind: TreeNodeKind = 'detail';
    children?: AlertItem[];

    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(label, collapsibleState);
    }
}

class AlertProvider implements vscode.TreeDataProvider<AlertItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<AlertItem | undefined | null | void> = new vscode.EventEmitter<AlertItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<AlertItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private alerts: Alert[] = [];
    private eventSource: any = null;
    private isConnected: boolean = false;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private reconnectDelay: number = 2000; // start at 2s
    private static readonly MAX_RECONNECT_DELAY = 60000; // cap at 60s
    private static readonly BASE_RECONNECT_DELAY = 2000;
    private lastEventTime: number = 0;
    private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    private static readonly HEARTBEAT_CHECK_INTERVAL = 10000; // check every 10s
    private static readonly HEARTBEAT_TIMEOUT = 45000; // no data for 45s = dead

    constructor() {
        // Don't auto-start here; activate() calls startListening()
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: AlertItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: AlertItem): Thenable<AlertItem[]> {
        if (!element) {
            // Root level — status + alerts
            const items: AlertItem[] = [];

            const statusItem = new AlertItem(
                this.isConnected ? '🟢 Connected' : '🔴 Disconnected',
                vscode.TreeItemCollapsibleState.None
            );
            statusItem.kind = 'status';
            statusItem.description = this.isConnected ? 'Live' : 'Retrying…';
            items.push(statusItem);

            if (this.alerts.length === 0) {
                const empty = new AlertItem('📭 No alerts yet', vscode.TreeItemCollapsibleState.None);
                empty.kind = 'empty';
                items.push(empty);
            } else {
                this.alerts.forEach((alert, index) => {
                    const alertItem = new AlertItem(
                        formatAlertLabel(alert),
                        vscode.TreeItemCollapsibleState.Collapsed
                    );
                    alertItem.id = `${alert.id}-${new Date(alert.received_at).getTime()}-${index}`;
                    alertItem.alert = alert;
                    alertItem.kind = 'alert';
                    alertItem.contextValue = 'alertItem';
                    alertItem.description = `${alert.cities.length} areas · ${formatRelativeTime(alert.received_at)}`;
                    alertItem.tooltip = new vscode.MarkdownString(
                        `**${formatAlertLabel(alert)}**\n\n` +
                        `📍 **${alert.cities.length} areas** — ${alert.cities.slice(0, 5).join(', ')}${alert.cities.length > 5 ? ' …' : ''}\n\n` +
                        `📋 ${alert.instructions}\n\n` +
                        `🕐 ${new Date(alert.received_at).toLocaleString()}`
                    );
                    items.push(alertItem);
                });
            }

            return Promise.resolve(items);
        }

        // If this node has pre-built children, return them
        if (element.children) {
            return Promise.resolve(element.children);
        }

        // Alert detail level
        if (element.kind === 'alert' && element.alert) {
            const alert = element.alert;
            const children: AlertItem[] = [];

            // Areas section — expandable list of cities
            const areasSection = new AlertItem(
                `📍 Areas (${alert.cities.length})`,
                vscode.TreeItemCollapsibleState.Collapsed
            );
            areasSection.kind = 'section';
            areasSection.children = alert.cities.map(city => {
                const cityItem = new AlertItem(city, vscode.TreeItemCollapsibleState.None);
                cityItem.kind = 'city';
                cityItem.iconPath = new vscode.ThemeIcon('location');
                return cityItem;
            });
            children.push(areasSection);

            // Instructions
            const instrItem = new AlertItem(
                `📋 ${alert.instructions || 'No instructions'}`,
                vscode.TreeItemCollapsibleState.None
            );
            instrItem.kind = 'detail';
            children.push(instrItem);

            // Timestamp
            const timeItem = new AlertItem(
                `🕐 ${new Date(alert.received_at).toLocaleString()}`,
                vscode.TreeItemCollapsibleState.None
            );
            timeItem.kind = 'detail';
            children.push(timeItem);

            return Promise.resolve(children);
        }

        return Promise.resolve([]);
    }

    startListening() {
        this.cancelReconnect();

        const config = vscode.workspace.getConfiguration('pikudHaoref');
        const apiUrl = config.get<string>('apiUrl', 'http://localhost:8002/api/alerts-stream');
        const apiKey = config.get<string>('apiKey', 'poha-test-key-2024-secure');
        const enableNotifications = config.get<boolean>('enableNotifications', true);

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        try {
            this.eventSource = new EventSource(apiUrl, {
                headers: {
                    'X-API-Key': apiKey
                }
            });

            this.eventSource.onopen = () => {
                this.isConnected = true;
                this.lastEventTime = Date.now();
                this.reconnectDelay = AlertProvider.BASE_RECONNECT_DELAY;
                this.startHeartbeatMonitor();
                this.refresh();
                vscode.window.showInformationMessage('🟢 Connected to Pikud Haoref alert stream');

                // Load recent history from DB on first connect
                if (this.alerts.length === 0) {
                    this.fetchAlertHistory();
                }
            };

            this.eventSource.onmessage = (event: any) => {
                try {
                    this.lastEventTime = Date.now();

                    // Update status if we were marked disconnected
                    if (!this.isConnected) {
                        this.isConnected = true;
                        this.refresh();
                    }

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
                        type: this.resolveType(alertData),
                        cities: alertData.cities || alertData.data || [],
                        instructions: alertData.instructions_en || alertData.instructions || alertData.title || 'Follow safety instructions',
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
                const wasConnected = this.isConnected;
                this.isConnected = false;

                // Close the built-in auto-reconnect; we manage our own
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }

                this.refresh();
                console.error('SSE connection error:', error);

                // Only show the error message once (on first disconnect)
                if (wasConnected) {
                    vscode.window.showErrorMessage('❌ Lost connection to alert stream. Will retry with backoff…');
                }

                this.scheduleReconnect();
            };

        } catch (error) {
            vscode.window.showErrorMessage(`Failed to connect to alert stream: ${error}`);
            this.scheduleReconnect();
        }
    }

    private scheduleReconnect() {
        this.cancelReconnect();
        const delay = this.reconnectDelay;
        console.log(`Scheduling SSE reconnect in ${delay / 1000}s`);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.startListening();
        }, delay);
        // Exponential backoff: 2s → 4s → 8s → 16s → 32s → 60s (cap)
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, AlertProvider.MAX_RECONNECT_DELAY);
    }

    private cancelReconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    private startHeartbeatMonitor() {
        this.stopHeartbeatMonitor();
        this.heartbeatTimer = setInterval(() => {
            if (!this.isConnected) {
                return;
            }
            const elapsed = Date.now() - this.lastEventTime;
            if (elapsed > AlertProvider.HEARTBEAT_TIMEOUT) {
                console.log(`No SSE data for ${Math.round(elapsed / 1000)}s — marking disconnected`);
                this.isConnected = false;
                this.refresh();
                // Force reconnect
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                this.stopHeartbeatMonitor();
                this.scheduleReconnect();
            }
        }, AlertProvider.HEARTBEAT_CHECK_INTERVAL);
    }

    private stopHeartbeatMonitor() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    stopListening() {
        this.cancelReconnect();
        this.stopHeartbeatMonitor();
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.reconnectDelay = AlertProvider.BASE_RECONNECT_DELAY;
        this.refresh();
        vscode.window.showInformationMessage('🔴 Disconnected from alert stream');
    }

    /** Fetch recent alert history from the REST API and populate the tree */
    private async fetchAlertHistory() {
        const config = vscode.workspace.getConfiguration('pikudHaoref');
        const apiKey = config.get<string>('apiKey', 'poha-test-key-2024-secure');
        const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');

        try {
            const url = `${serverUrl.replace(/\/+$/, '')}/api/alerts/history?limit=20`;
            const response = await fetch(url, {
                headers: { 'X-API-Key': apiKey },
            });
            if (!response.ok) {
                console.error(`History fetch failed: HTTP ${response.status}`);
                return;
            }
            const body = await response.json() as { alerts: any[]; count: number };
            if (!body.alerts || body.alerts.length === 0) {
                return;
            }

            // Convert DB rows → Alert objects (avoid duplicating IDs already shown)
            const existingIds = new Set(this.alerts.map(a => a.id));
            for (const row of body.alerts) {
                if (existingIds.has(row.id)) { continue; }
                this.alerts.push({
                    id: row.id,
                    type: this.resolveType(row),
                    cities: row.data || [],
                    instructions: row.title || row.desc || 'Follow safety instructions',
                    received_at: row.timestamp || new Date().toISOString(),
                });
            }

            if (this.alerts.length > 50) {
                this.alerts = this.alerts.slice(0, 50);
            }
            this.refresh();
            console.log(`Loaded ${body.alerts.length} historical alerts from DB`);
        } catch (err: any) {
            console.error('Failed to fetch alert history:', err.message);
        }
    }

    /** Resolve human-readable type from various data shapes */
    private resolveType(data: any): string {
        // SSE structured alert: has "type" like "missiles"
        if (data.type && ALERT_TYPE_LABELS[data.type]) {
            return data.type;
        }
        // DB row: has "category" (cat number as string)
        if (data.category || data.cat) {
            const cat = parseInt(data.category || data.cat, 10);
            const mapped = this.catToType(cat);
            if (mapped) { return mapped; }
        }
        // Fallback
        if (data.title_en) { return data.title_en; }
        if (data.type) { return data.type; }
        return 'unknown';
    }

    private catToType(cat: number): string | undefined {
        const map: Record<number, string> = {
            1: 'missiles', 2: 'radiologicalEvent', 3: 'earthQuake',
            4: 'tsunami', 5: 'hostileAircraftIntrusion', 6: 'hazardousMaterials',
            7: 'terroristInfiltration', 8: 'missilesDrill', 9: 'earthQuakeDrill',
            10: 'radiologicalEventDrill', 11: 'tsunamiDrill',
            12: 'hostileAircraftIntrusionDrill', 13: 'hazardousMaterialsDrill',
            14: 'terroristInfiltrationDrill', 20: 'newsFlash',
        };
        return map[cat];
    }

    deleteAlert(itemToDelete: AlertItem) {
        if (!itemToDelete.id) {
            return;
        }
        const index = this.alerts.findIndex((alert, idx) => {
            const expectedId = `${alert.id}-${new Date(alert.received_at).getTime()}-${idx}`;
            return itemToDelete.id === expectedId;
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
        const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');
        
        const postData = JSON.stringify({
            data: ['VS Code Extension Test'],
            cat: '1',
            language: 'en'
        });

        try {
            const url = `${serverUrl.replace(/\/+$/, '')}/api/test/fake-alert`;
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': apiKey,
                },
                body: postData,
            });
            if (response.ok) {
                const result = await response.json() as { alert_id?: string };
                vscode.window.showInformationMessage(`✅ Test alert sent: ${result.alert_id}`);
            } else {
                vscode.window.showErrorMessage(`❌ HTTP ${response.status}`);
            }
        } catch (error: any) {
            vscode.window.showErrorMessage(`❌ Failed to send test alert: ${error.message}`);
        }
    }

    clearAllAlerts() {
        this.alerts = [];
        this.refresh();
        vscode.window.showInformationMessage('All alerts cleared');
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
        vscode.commands.registerCommand('pikudHaoref.clearAllAlerts', () => alertProvider.clearAllAlerts()),
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

    // Auto-reconnect when settings change
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('pikudHaoref.apiUrl') || e.affectsConfiguration('pikudHaoref.serverUrl')) {
                alertProvider.startListening();
            }
        })
    );

    // Auto-start listening on activation
    alertProvider.startListening();

    vscode.window.showInformationMessage('🚨 Pikud Haoref Alert Monitor activated');
}

export function deactivate() {
    // Handled by disposables, but also close any active EventSource
    // The AlertProvider's stopListening is called via subscriptions disposal
}