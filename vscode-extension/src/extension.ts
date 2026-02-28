import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';

const EventSource = require('eventsource');

interface Alert {
    id: string;
    type: string;
    cities: string[];
    instructions: string;
    received_at: string;
}

// Map internal type codes to human-readable labels with icons
const ALERT_TYPE_LABELS: Record<string, { label: string; icon: string; svgIcon: string }> = {
    missiles:                    { label: 'Missile Threat',             icon: '🚀', svgIcon: 'missiles.svg' },
    radiologicalEvent:           { label: 'Radiological Event',         icon: '☢️', svgIcon: 'radiological.svg' },
    earthQuake:                  { label: 'Earthquake',                 icon: '🌍', svgIcon: 'earthquake.svg' },
    tsunami:                     { label: 'Tsunami',                    icon: '🌊', svgIcon: 'tsunami.svg' },
    hostileAircraftIntrusion:    { label: 'Hostile Aircraft Intrusion',  icon: '✈️', svgIcon: 'aircraft.svg' },
    hazardousMaterials:          { label: 'Hazardous Materials',        icon: '⚠️', svgIcon: 'hazmat.svg' },
    terroristInfiltration:       { label: 'Terrorist Infiltration',     icon: '🔫', svgIcon: 'terrorist.svg' },
    missilesDrill:               { label: 'Drill — Missile',            icon: '🔔', svgIcon: 'drill.svg' },
    earthQuakeDrill:             { label: 'Drill — Earthquake',         icon: '🔔', svgIcon: 'drill.svg' },
    radiologicalEventDrill:      { label: 'Drill — Radiological',       icon: '🔔', svgIcon: 'drill.svg' },
    tsunamiDrill:                { label: 'Drill — Tsunami',            icon: '🔔', svgIcon: 'drill.svg' },
    hostileAircraftIntrusionDrill:{ label: 'Drill — Aircraft',          icon: '🔔', svgIcon: 'drill.svg' },
    hazardousMaterialsDrill:     { label: 'Drill — Hazmat',             icon: '🔔', svgIcon: 'drill.svg' },
    terroristInfiltrationDrill:  { label: 'Drill — Infiltration',       icon: '🔔', svgIcon: 'drill.svg' },
    allClear:                    { label: 'All Clear — Safe to Exit',   icon: '✅', svgIcon: 'all-clear.svg' },
    newsFlash:                   { label: 'News Flash',                 icon: '📰', svgIcon: 'news.svg' },
    unknown:                     { label: 'Alert',                      icon: '🚨', svgIcon: 'alert.svg' },
};

function formatAlertLabel(alert: Alert): string {
    const info = ALERT_TYPE_LABELS[alert.type] || ALERT_TYPE_LABELS['unknown'];
    return `${info.icon} ${info.label}`;
}

/** Get the SVG icon URI for an alert type */
function getAlertIconPath(extensionPath: string, alertType: string): vscode.Uri {
    const info = ALERT_TYPE_LABELS[alertType] || ALERT_TYPE_LABELS['unknown'];
    return vscode.Uri.file(path.join(extensionPath, 'resources', 'icons', info.svgIcon));
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

/** Return the absolute path to the sounds/ directory inside the extension */
function getSoundsDir(extensionPath: string): string {
    return path.join(extensionPath, 'sounds');
}

/** Scan sounds/ folder for .mp3 files */
function discoverSounds(extensionPath: string): string[] {
    const dir = getSoundsDir(extensionPath);
    try {
        return fs.readdirSync(dir)
            .filter(f => f.toLowerCase().endsWith('.mp3'))
            .sort();
    } catch {
        return [];
    }
}

/** Play an MP3 file using the OS audio command */
function playSound(filePath: string): void {
    const platform = process.platform;
    if (platform === 'darwin') {
        execFile('afplay', [filePath], (err) => {
            if (err) { console.error('Sound playback error:', err.message); }
        });
    } else if (platform === 'linux') {
        // Try paplay (PulseAudio) first, fall back to aplay
        execFile('paplay', [filePath], (err) => {
            if (err) {
                execFile('aplay', [filePath], (err2) => {
                    if (err2) { console.error('Sound playback error:', err2.message); }
                });
            }
        });
    } else if (platform === 'win32') {
        execFile('powershell', ['-c', `(New-Object Media.SoundPlayer '${filePath}').PlaySync()`], (err) => {
            if (err) { console.error('Sound playback error:', err.message); }
        });
    }
}

/** Tree item types to distinguish children in getChildren() */
type TreeNodeKind = 'status' | 'empty' | 'alert' | 'section' | 'city' | 'detail' | 'controls' | 'soundToggle' | 'soundPicker' | 'filterHeader' | 'filterArea';

class AlertItem extends vscode.TreeItem {
    alert?: Alert;
    kind: TreeNodeKind = 'detail';
    children?: AlertItem[];
    areaName?: string; // used for filterArea items to know which area to remove

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
    private extensionPath: string = '';
    private knownCities: Set<string> = new Set();

    constructor() {
        // Don't auto-start here; activate() calls startListening()
    }

    /** Get all unique cities seen across all alerts */
    getKnownCities(): string[] {
        return [...this.knownCities].sort();
    }

    /** Track cities from an alert */
    private trackCities(cities: string[]) {
        for (const city of cities) {
            this.knownCities.add(city);
        }
    }

    /** Check if an alert matches the area filter (empty filter = match all) */
    private matchesAreaFilter(alert: Alert): boolean {
        const config = vscode.workspace.getConfiguration('pikudHaoref');
        const filterAreas = config.get<string[]>('filterAreas', []);
        if (filterAreas.length === 0) { return true; }
        return alert.cities.some(city =>
            filterAreas.some(area => city.includes(area) || area.includes(city))
        );
    }

    setExtensionPath(extPath: string) {
        this.extensionPath = extPath;
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: AlertItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: AlertItem): Thenable<AlertItem[]> {
        if (!element) {
            // Root level — status + controls + alerts
            const items: AlertItem[] = [];

            // --- Status ---
            const statusItem = new AlertItem(
                this.isConnected ? '🟢 Connected' : '🔴 Disconnected',
                vscode.TreeItemCollapsibleState.None
            );
            statusItem.kind = 'status';
            statusItem.description = this.isConnected ? 'Live' : 'Retrying…';
            items.push(statusItem);

            // --- Controls panel ---
            const controlsItem = new AlertItem(
                '⚙️ Controls',
                vscode.TreeItemCollapsibleState.Collapsed
            );
            controlsItem.kind = 'controls';
            controlsItem.id = 'controls-panel';
            items.push(controlsItem);

            // --- Alerts ---
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
                    if (this.extensionPath) {
                        alertItem.iconPath = getAlertIconPath(this.extensionPath, alert.type);
                    }
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

        // Controls panel children
        if (element.kind === 'controls') {
            const config = vscode.workspace.getConfiguration('pikudHaoref');
            const children: AlertItem[] = [];

            // Sound toggle
            const enableSound = config.get<boolean>('enableSound', true);
            const alertSoundFile = config.get<string>('alertSound', 'worms.mp3');
            const soundToggle = new AlertItem(
                enableSound ? '🔊 Sound: ON' : '🔇 Sound: OFF',
                vscode.TreeItemCollapsibleState.None
            );
            soundToggle.kind = 'soundToggle';
            soundToggle.id = 'ctrl-sound-toggle';
            soundToggle.description = enableSound ? alertSoundFile : 'click to enable';
            soundToggle.contextValue = 'soundToggle';
            soundToggle.command = { command: 'pikudHaoref.toggleSound', title: 'Toggle Sound' };
            soundToggle.tooltip = 'Click to toggle alert sound on/off';
            children.push(soundToggle);

            // Sound picker
            const soundPicker = new AlertItem(
                '🎵 Change Sound',
                vscode.TreeItemCollapsibleState.None
            );
            soundPicker.kind = 'soundPicker';
            soundPicker.id = 'ctrl-sound-picker';
            soundPicker.description = alertSoundFile;
            soundPicker.contextValue = 'soundPicker';
            soundPicker.command = { command: 'pikudHaoref.selectAlertSound', title: 'Select Sound' };
            soundPicker.tooltip = 'Click to choose alert sound file';
            children.push(soundPicker);

            // Filter header
            const filterAreas = config.get<string[]>('filterAreas', []);
            const filterHeader = new AlertItem(
                '📍 Area Filter',
                filterAreas.length > 0 ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None
            );
            filterHeader.kind = 'filterHeader';
            filterHeader.id = 'ctrl-filter-header';
            filterHeader.description = filterAreas.length === 0 ? 'All areas (click to set)' : `${filterAreas.length} areas`;
            filterHeader.contextValue = 'filterHeader';
            filterHeader.command = { command: 'pikudHaoref.selectFilterAreas', title: 'Edit Filter' };
            filterHeader.tooltip = 'Click to select which areas trigger alerts';
            if (filterAreas.length > 0) {
                filterHeader.children = filterAreas.map(area => {
                    const areaItem = new AlertItem(area, vscode.TreeItemCollapsibleState.None);
                    areaItem.kind = 'filterArea';
                    areaItem.id = `ctrl-filter-${area}`;
                    areaItem.areaName = area;
                    areaItem.contextValue = 'filterArea';
                    areaItem.iconPath = new vscode.ThemeIcon('location');
                    areaItem.tooltip = `Click × to remove ${area} from filter`;
                    return areaItem;
                });
            }
            children.push(filterHeader);

            return Promise.resolve(children);
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

                    // Track all cities we've ever seen
                    this.trackCities(alert.cities);

                    // Add to beginning of array (most recent first)
                    this.alerts.unshift(alert);
                    
                    // Keep only last 50 alerts
                    if (this.alerts.length > 50) {
                        this.alerts = this.alerts.slice(0, 50);
                    }

                    this.refresh();

                    // Check area filter — notifications + sound only for matching areas
                    const alertMatchesFilter = this.matchesAreaFilter(alert);

                    // Show notification if enabled and area matches
                    if (enableNotifications && alertMatchesFilter) {
                        const message = `🚨 EMERGENCY ALERT: ${alert.cities.join(', ')} - ${alert.type}`;
                        vscode.window.showWarningMessage(message, 'View Details').then(selection => {
                            if (selection === 'View Details') {
                                vscode.commands.executeCommand('workbench.view.explorer');
                            }
                        });
                    }

                    // Play alert sound if enabled and area matches
                    if (alertMatchesFilter) {
                        const soundConfig = vscode.workspace.getConfiguration('pikudHaoref');
                        const enableSound = soundConfig.get<boolean>('enableSound', true);
                        const alertSoundFile = soundConfig.get<string>('alertSound', 'worms.mp3');
                        if (enableSound && alertSoundFile && this.extensionPath) {
                            const soundPath = path.join(getSoundsDir(this.extensionPath), alertSoundFile);
                            if (fs.existsSync(soundPath)) {
                                playSound(soundPath);
                            }
                        }
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
                const cities = row.data || [];
                this.trackCities(cities);
                this.alerts.push({
                    id: row.id,
                    type: this.resolveType(row),
                    cities,
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
        // Check all text fields for "all clear" indicators
        // Real data from oref.org.il uses these exact phrases:
        //   "ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו"
        //   "חדירת כלי טיס עוין - האירוע הסתיים"
        const textFields = [
            data.title, data.title_en, data.instructions, data.desc
        ].filter(Boolean).join(' ');
        const allClearKeywords = [
            'ניתן לצאת',          // "ניתן לצאת מהמרחב המוגן..."
            'האירוע הסתיים',      // "חדירת כלי טיס עוין - האירוע הסתיים"
            'חזרה לשגרה',         // general all-clear
            'all clear',
            'safe to exit',
        ];
        if (allClearKeywords.some(kw => textFields.includes(kw))) {
            return 'allClear';
        }

        // Map known Hebrew titles to types (as they arrive from SSE relay)
        const hebrewTitleMap: Record<string, string> = {
            'ירי רקטות וטילים': 'missiles',
            'התרעת צבע אדום': 'missiles',
            'חדירת כלי טיס עוין': 'hostileAircraftIntrusion',
            'רעידת אדמה': 'earthQuake',
            'צונאמי': 'tsunami',
            'אירוע רדיולוגי': 'radiologicalEvent',
            'חומרים מסוכנים': 'hazardousMaterials',
            'חדירת מחבלים': 'terroristInfiltration',
        };
        for (const field of [data.title, data.instructions]) {
            if (field && hebrewTitleMap[field]) {
                return hebrewTitleMap[field];
            }
        }

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
    alertProvider.setExtensionPath(context.extensionPath);
    
    // Register tree data provider
    vscode.window.registerTreeDataProvider('pikudHaorefAlerts', alertProvider);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('pikudHaoref.startAlerts', () => alertProvider.startListening()),
        vscode.commands.registerCommand('pikudHaoref.stopAlerts', () => alertProvider.stopListening()),
        vscode.commands.registerCommand('pikudHaoref.testAlert', () => alertProvider.sendTestAlert()),
        vscode.commands.registerCommand('pikudHaoref.deleteAlert', (item: AlertItem) => alertProvider.deleteAlert(item)),
        vscode.commands.registerCommand('pikudHaoref.clearAllAlerts', () => alertProvider.clearAllAlerts()),
        vscode.commands.registerCommand('pikudHaoref.toggleSound', async () => {
            const config = vscode.workspace.getConfiguration('pikudHaoref');
            const current = config.get<boolean>('enableSound', true);
            await config.update('enableSound', !current, vscode.ConfigurationTarget.Global);
            alertProvider.refresh();
            vscode.window.showInformationMessage(current ? '🔇 Alert sound disabled' : '🔊 Alert sound enabled');
        }),
        vscode.commands.registerCommand('pikudHaoref.removeFilterArea', async (item: AlertItem) => {
            if (!item.areaName) { return; }
            const config = vscode.workspace.getConfiguration('pikudHaoref');
            const current = config.get<string[]>('filterAreas', []);
            const updated = current.filter(a => a !== item.areaName);
            await config.update('filterAreas', updated, vscode.ConfigurationTarget.Global);
            alertProvider.refresh();
            vscode.window.showInformationMessage(`📍 Removed "${item.areaName}" from filter`);
        }),
        vscode.commands.registerCommand('pikudHaoref.selectFilterAreas', async () => {
            const config = vscode.workspace.getConfiguration('pikudHaoref');
            const currentFilter = config.get<string[]>('filterAreas', []);
            const allCities = alertProvider.getKnownCities();

            // Merge known cities + current filter (in case filter has cities not yet seen)
            const allOptions = [...new Set([...allCities, ...currentFilter])].sort();

            if (allOptions.length === 0) {
                // No history yet — allow manual entry
                const input = await vscode.window.showInputBox({
                    prompt: 'Enter area names separated by commas (no alerts received yet to pick from)',
                    placeHolder: 'e.g. תל אביב, רמת גן, חיפה'
                });
                if (input) {
                    const areas = input.split(',').map(s => s.trim()).filter(Boolean);
                    await config.update('filterAreas', areas, vscode.ConfigurationTarget.Global);
                    alertProvider.refresh();
                    vscode.window.showInformationMessage(`📍 Area filter set: ${areas.join(', ')}`);
                }
                return;
            }

            const items = allOptions.map(city => ({
                label: city,
                picked: currentFilter.includes(city)
            }));

            const picked = await vscode.window.showQuickPick(items, {
                canPickMany: true,
                placeHolder: 'Select areas to filter alerts (empty = all alerts)',
                title: 'Alert Area Filter'
            });

            if (picked !== undefined) {
                const selectedAreas = picked.map(p => p.label);
                await config.update('filterAreas', selectedAreas, vscode.ConfigurationTarget.Global);
                alertProvider.refresh();
                if (selectedAreas.length === 0) {
                    vscode.window.showInformationMessage('📍 Area filter cleared — receiving all alerts');
                } else {
                    vscode.window.showInformationMessage(`📍 Area filter set: ${selectedAreas.join(', ')}`);
                }
            }
        }),
        vscode.commands.registerCommand('pikudHaoref.selectAlertSound', async () => {
            const sounds = discoverSounds(context.extensionPath);
            if (sounds.length === 0) {
                vscode.window.showWarningMessage('No .mp3 files found in the sounds/ folder.');
                return;
            }
            const config = vscode.workspace.getConfiguration('pikudHaoref');
            const current = config.get<string>('alertSound', '');
            const items = sounds.map(s => ({
                label: s === current ? `$(check) ${s}` : s,
                description: s === current ? 'currently selected' : '',
                file: s
            }));
            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: 'Select an alert sound (.mp3)',
                title: 'Alert Sound'
            });
            if (picked) {
                await config.update('alertSound', picked.file, vscode.ConfigurationTarget.Global);
                alertProvider.refresh();
                vscode.window.showInformationMessage(`🔊 Alert sound set to: ${picked.file}`);
            }
        }),
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

    // Auto-reconnect when settings change, refresh controls when sound/filter changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('pikudHaoref.apiUrl') || e.affectsConfiguration('pikudHaoref.serverUrl')) {
                alertProvider.startListening();
            }
            if (e.affectsConfiguration('pikudHaoref.enableSound') ||
                e.affectsConfiguration('pikudHaoref.alertSound') ||
                e.affectsConfiguration('pikudHaoref.filterAreas')) {
                alertProvider.refresh();
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