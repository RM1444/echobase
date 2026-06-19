import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const DBUS_INTERFACE = `
<node>
  <interface name="org.EchoBase.Grid">
    <!-- Grid overlay -->
    <method name="Show">
      <arg type="i" direction="in" name="width"/>
      <arg type="i" direction="in" name="height"/>
    </method>
    <method name="Hide"/>
    <method name="Update">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
      <arg type="i" direction="in" name="width"/>
      <arg type="i" direction="in" name="height"/>
    </method>
    
    <!-- Mouse control -->
    <method name="Click">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="DoubleClick">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="TripleClick">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="RightClick">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="MiddleClick">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="MoveTo">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="StartDrag">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="EndDrag">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="Scroll">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
      <arg type="s" direction="in" name="direction"/>
      <arg type="i" direction="in" name="clicks"/>
    </method>

    <!-- Numbered click-hints over native UI elements -->
    <method name="ShowHints">
      <arg type="s" direction="in" name="hintsJson"/>
    </method>
    <method name="HideHints"/>

    <!-- Numbered window picker overlay -->
    <method name="ShowWindowPicker">
      <arg type="s" direction="in" name="itemsJson"/>
    </method>
    <method name="HideWindowPicker"/>

    <!-- Dwell-click countdown indicator -->
    <method name="ShowDwell">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
      <arg type="d" direction="in" name="fraction"/>
    </method>
    <method name="HideDwell"/>

    <!-- Keyboard control -->
    <method name="PressKey">
      <arg type="s" direction="in" name="name"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
    <method name="KeyCombo">
      <arg type="s" direction="in" name="combo"/>
      <arg type="b" direction="out" name="ok"/>
    </method>

    <!-- Screenshot for OCR -->
    <method name="TakeScreenshot">
      <arg type="s" direction="out" name="path"/>
    </method>
    
    <!-- Window management (focused window) -->
    <method name="CloseWindow"/>
    <method name="MinimizeWindow"/>
    <method name="MaximizeWindow"/>
    <method name="UnmaximizeWindow"/>
    <method name="FullscreenWindow"/>
    <method name="UnfullscreenWindow"/>
    <method name="TileLeft"/>
    <method name="TileRight"/>
    
    <!-- Window queries and focus -->
    <method name="GetWindows">
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="FocusWindow">
      <arg type="s" direction="in" name="title"/>
      <arg type="b" direction="out" name="success"/>
    </method>
    
    <!-- Workspace control -->
    <method name="SwitchWorkspace">
      <arg type="i" direction="in" name="index"/>
    </method>
    <method name="NextWorkspace"/>
    <method name="PrevWorkspace"/>
    <method name="GetWorkspaceCount">
      <arg type="i" direction="out" name="count"/>
    </method>
    <method name="GetCurrentWorkspace">
      <arg type="i" direction="out" name="index"/>
    </method>
    
    <!-- Screen info -->
    <method name="GetScreenSize">
      <arg type="i" direction="out" name="width"/>
      <arg type="i" direction="out" name="height"/>
    </method>
    <method name="GetMonitors">
      <arg type="s" direction="out" name="monitorsJson"/>
    </method>
  </interface>
</node>`;

class GridOverlay {
    constructor() {
        this.container = null;
        this.bounds = [0, 0, 1920, 1080];
        this.screenW = 1920;
        this.screenH = 1080;
        this.workArea = null;
        this._pointer = null;
        this._dragging = false;
    }

    _getPointer() {
        if (!this._pointer) {
            const seat = Clutter.get_default_backend().get_default_seat();
            this._pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        }
        return this._pointer;
    }

    _clampToWorkArea(x, y, w, h) {
        if (!this.workArea) return [x, y, w, h];
        const wa = this.workArea;
        let newX = Math.max(wa.x, Math.min(x, wa.x + wa.width - w));
        let newY = Math.max(wa.y, Math.min(y, wa.y + wa.height - h));
        return [newX, newY, w, h];
    }

    show(width, height) {
        if (this.container) this.hide();

        const monitor = Main.layoutManager.primaryMonitor;
        // Use monitor's actual dimensions, ignore what Python sends
        this.screenW = monitor.width;
        this.screenH = monitor.height;
        
        this.bounds = [0, 0, this.screenW, this.screenH];

        this.container = new St.Widget({
            reactive: false,
            x: monitor.x,
            y: monitor.y,
            width: this.screenW,
            height: this.screenH,
        });

        this._draw();
        Main.uiGroup.add_child(this.container);
        
        log(`EchoBase: Grid shown ${this.screenW}x${this.screenH} at (${monitor.x},${monitor.y})`);
    }

    getScreenSize() {
        const monitor = Main.layoutManager.primaryMonitor;
        return [monitor.width, monitor.height];
    }

    getMonitors() {
        // Every monitor's geometry in the global logical coordinate space —
        // the same space notify_absolute_motion (moveTo) uses — so the Python
        // side can drive the pointer onto any display.
        const primaryIndex = Main.layoutManager.primaryIndex;
        const monitors = Main.layoutManager.monitors.map((m, i) => ({
            index: i,
            x: m.x,
            y: m.y,
            width: m.width,
            height: m.height,
            primary: i === primaryIndex,
        }));
        return JSON.stringify(monitors);
    }

    hide() {
        if (this.container) {
            this.container.destroy();
            this.container = null;
        }
    }

    update(x, y, width, height) {
        if (!this.container) return;
        this.bounds = [x, y, width, height];
        this._draw();
    }

    click(x, y) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        pointer.notify_button(t + 10000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
    }

    doubleClick(x, y) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        pointer.notify_button(t + 10000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
        pointer.notify_button(t + 60000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        pointer.notify_button(t + 65000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
    }

    tripleClick(x, y) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        for (let i = 0; i < 3; i++) {
            const base = t + 5000 + i * 55000;
            pointer.notify_button(base, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
            pointer.notify_button(base + 5000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
        }
    }

    rightClick(x, y) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_SECONDARY, Clutter.ButtonState.PRESSED);
        pointer.notify_button(t + 10000, Clutter.BUTTON_SECONDARY, Clutter.ButtonState.RELEASED);
    }

    middleClick(x, y) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_MIDDLE, Clutter.ButtonState.PRESSED);
        pointer.notify_button(t + 10000, Clutter.BUTTON_MIDDLE, Clutter.ButtonState.RELEASED);
    }

    moveTo(x, y) {
        const pointer = this._getPointer();
        pointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
    }

    startDrag(x, y) {
        // Keep grid visible so user can navigate to end point
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        this._dragging = true;
    }

    endDrag(x, y) {
        if (!this._dragging) return;
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);
        pointer.notify_button(t + 5000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
        this._dragging = false;
    }

    scroll(x, y, direction, clicks) {
        this.hide();
        const pointer = this._getPointer();
        const t = GLib.get_monotonic_time();
        pointer.notify_absolute_motion(t, x, y);

        let dx = 0, dy = 0;
        const scrollAmount = 1;
        switch (direction) {
            case 'up': dy = -scrollAmount; break;
            case 'down': dy = scrollAmount; break;
            case 'left': dx = -scrollAmount; break;
            case 'right': dx = scrollAmount; break;
        }

        for (let i = 0; i < clicks; i++) {
            pointer.notify_scroll_continuous(t + (i * 50000), dx, dy,
                Clutter.ScrollSource.FINGER, Clutter.ScrollFinishFlags.NONE);
        }
    }

    _draw() {
        this.container.destroy_all_children();
        const [bx, by, bw, bh] = this.bounds;

        // Frosted glass overlay background
        this.container.add_child(new St.Widget({
            style: 'background-color: rgba(15, 23, 42, 0.25); ' +
                'border: 1px solid rgba(148, 163, 184, 0.2);',
            x: bx, y: by, width: bw, height: bh
        }));

        // Grid geometry
        const cellW = Math.floor(bw / 3);
        const cellH = Math.floor(bh / 3);

        // Subtle grid lines with glow effect
        for (let i = 1; i < 3; i++) {
            // Vertical line glow
            this.container.add_child(new St.Widget({
                style: 'background-color: rgba(99, 179, 237, 0.15);',
                x: bx + i * cellW - 4, y: by, width: 9, height: bh
            }));
            // Vertical line core
            this.container.add_child(new St.Widget({
                style: 'background-color: rgba(147, 197, 253, 0.6);',
                x: bx + i * cellW, y: by, width: 1, height: bh
            }));

            // Horizontal line glow
            this.container.add_child(new St.Widget({
                style: 'background-color: rgba(99, 179, 237, 0.15);',
                x: bx, y: by + i * cellH - 4, width: bw, height: 9
            }));
            // Horizontal line core
            this.container.add_child(new St.Widget({
                style: 'background-color: rgba(147, 197, 253, 0.6);',
                x: bx, y: by + i * cellH, width: bw, height: 1
            }));
        }

        // Corner brackets for bounding region
        const cornerLen = Math.min(30, Math.floor(Math.min(bw, bh) / 10));
        const cornerThick = 2;
        const cornerStyle = 'background-color: rgba(186, 230, 253, 0.8);';
        const corners = [
            [bx, by], [bx + bw - cornerLen, by],
            [bx, by + bh - cornerLen], [bx + bw - cornerLen, by + bh - cornerLen]
        ];
        // Top-left
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx, y: by, width: cornerLen, height: cornerThick }));
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx, y: by, width: cornerThick, height: cornerLen }));
        // Top-right
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx + bw - cornerLen, y: by, width: cornerLen, height: cornerThick }));
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx + bw - cornerThick, y: by, width: cornerThick, height: cornerLen }));
        // Bottom-left
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx, y: by + bh - cornerThick, width: cornerLen, height: cornerThick }));
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx, y: by + bh - cornerLen, width: cornerThick, height: cornerLen }));
        // Bottom-right
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx + bw - cornerLen, y: by + bh - cornerThick, width: cornerLen, height: cornerThick }));
        this.container.add_child(new St.Widget({ style: cornerStyle, x: bx + bw - cornerThick, y: by + bh - cornerLen, width: cornerThick, height: cornerLen }));

        // Number labels 1-9
        const fontSize = Math.max(20, Math.min(56, Math.floor(Math.min(cellW, cellH) / 4)));
        const badgePad = Math.max(6, Math.floor(fontSize / 4));
        for (let num = 1; num <= 9; num++) {
            const row = Math.floor((num - 1) / 3);
            const col = (num - 1) % 3;
            const zoneX = bx + col * cellW;
            const zoneY = by + row * cellH;

            const label = new St.Label({
                text: String(num),
                style: `font-size: ${fontSize}px; font-weight: 600; color: #f0f9ff; ` +
                    `background-color: rgba(30, 58, 138, 0.75); ` +
                    `border: 1px solid rgba(147, 197, 253, 0.5); ` +
                    `border-radius: ${fontSize}px; ` +
                    `padding: ${badgePad}px ${badgePad * 2}px; ` +
                    `text-align: center; ` +
                    `box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);`
            });

            label.set_position(
                zoneX + Math.floor(cellW / 2) - Math.floor(fontSize / 2) - badgePad,
                zoneY + Math.floor(cellH / 2) - Math.floor(fontSize / 2) - badgePad
            );
            this.container.add_child(label);
        }

        // Modern crosshair at center
        const centerX = bx + Math.floor(bw / 2);
        const centerY = by + Math.floor(bh / 2);
        const crossSize = Math.min(40, Math.floor(Math.min(bw, bh) / 4));
        const crossThick = 2;
        const gapSize = 6;

        // Crosshair glow
        const glowStyle = 'background-color: rgba(56, 189, 248, 0.3);';
        this.container.add_child(new St.Widget({
            style: glowStyle,
            x: centerX - crossSize / 2 - 1, y: centerY - (crossThick + 2) / 2,
            width: crossSize - gapSize, height: crossThick + 2
        }));
        this.container.add_child(new St.Widget({
            style: glowStyle,
            x: centerX + gapSize / 2 + 1, y: centerY - (crossThick + 2) / 2,
            width: crossSize - gapSize, height: crossThick + 2
        }));
        this.container.add_child(new St.Widget({
            style: glowStyle,
            x: centerX - (crossThick + 2) / 2, y: centerY - crossSize / 2 - 1,
            width: crossThick + 2, height: crossSize - gapSize
        }));
        this.container.add_child(new St.Widget({
            style: glowStyle,
            x: centerX - (crossThick + 2) / 2, y: centerY + gapSize / 2 + 1,
            width: crossThick + 2, height: crossSize - gapSize
        }));

        // Crosshair lines (4 segments with center gap)
        const crossStyle = 'background-color: rgba(224, 242, 254, 0.95);';
        // Left arm
        this.container.add_child(new St.Widget({
            style: crossStyle,
            x: centerX - crossSize / 2, y: centerY - crossThick / 2,
            width: crossSize / 2 - gapSize / 2, height: crossThick
        }));
        // Right arm
        this.container.add_child(new St.Widget({
            style: crossStyle,
            x: centerX + gapSize / 2, y: centerY - crossThick / 2,
            width: crossSize / 2 - gapSize / 2, height: crossThick
        }));
        // Top arm
        this.container.add_child(new St.Widget({
            style: crossStyle,
            x: centerX - crossThick / 2, y: centerY - crossSize / 2,
            width: crossThick, height: crossSize / 2 - gapSize / 2
        }));
        // Bottom arm
        this.container.add_child(new St.Widget({
            style: crossStyle,
            x: centerX - crossThick / 2, y: centerY + gapSize / 2,
            width: crossThick, height: crossSize / 2 - gapSize / 2
        }));

        // Center dot
        const dotSize = 4;
        this.container.add_child(new St.Widget({
            style: 'background-color: rgba(56, 189, 248, 0.95); border-radius: 3px;',
            x: centerX - dotSize / 2, y: centerY - dotSize / 2,
            width: dotSize, height: dotSize
        }));
    }
}

class WindowManager {
    _getFocusedWindow() {
        return global.display.focus_window;
    }

    closeWindow() {
        const win = this._getFocusedWindow();
        if (win) win.delete(global.get_current_time());
    }

    minimizeWindow() {
        const win = this._getFocusedWindow();
        if (win) win.minimize();
    }

    maximizeWindow() {
        const win = this._getFocusedWindow();
        if (win) win.maximize(Meta.MaximizeFlags.BOTH);
    }

    unmaximizeWindow() {
        const win = this._getFocusedWindow();
        if (win) win.unmaximize(Meta.MaximizeFlags.BOTH);
    }

    fullscreenWindow() {
        const win = this._getFocusedWindow();
        if (win) win.make_fullscreen();
    }

    unfullscreenWindow() {
        const win = this._getFocusedWindow();
        if (win) win.unmake_fullscreen();
    }

    tileLeft() {
        const win = this._getFocusedWindow();
        if (!win) return;
        
        const monitor = win.get_monitor();
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor);
        
        win.unmaximize(Meta.MaximizeFlags.BOTH);
        win.move_resize_frame(
            false,
            workArea.x,
            workArea.y,
            Math.floor(workArea.width / 2),
            workArea.height
        );
    }

    tileRight() {
        const win = this._getFocusedWindow();
        if (!win) return;
        
        const monitor = win.get_monitor();
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor);
        
        win.unmaximize(Meta.MaximizeFlags.BOTH);
        win.move_resize_frame(
            false,
            workArea.x + Math.floor(workArea.width / 2),
            workArea.y,
            Math.floor(workArea.width / 2),
            workArea.height
        );
    }

    getWindows() {
        const windows = global.get_window_actors().map(actor => {
            const win = actor.get_meta_window();
            if (!win || win.get_window_type() !== Meta.WindowType.NORMAL) return null;
            return {
                id: win.get_id(),
                title: win.get_title(),
                wm_class: win.get_wm_class(),
                workspace: win.get_workspace()?.index() ?? -1,
                focused: win === this._getFocusedWindow()
            };
        }).filter(w => w !== null);
        
        return JSON.stringify(windows);
    }

    focusWindow(titleSubstring) {
        const lowerTitle = titleSubstring.toLowerCase();
        const actors = global.get_window_actors();
        
        for (const actor of actors) {
            const win = actor.get_meta_window();
            if (!win || win.get_window_type() !== Meta.WindowType.NORMAL) continue;
            
            const title = win.get_title()?.toLowerCase() || '';
            const wmClass = win.get_wm_class()?.toLowerCase() || '';
            
            if (title.includes(lowerTitle) || wmClass.includes(lowerTitle)) {
                win.activate(global.get_current_time());
                return true;
            }
        }
        return false;
    }

    switchWorkspace(index) {
        const workspaceManager = global.workspace_manager;
        const ws = workspaceManager.get_workspace_by_index(index);
        if (ws) ws.activate(global.get_current_time());
    }

    nextWorkspace() {
        const workspaceManager = global.workspace_manager;
        const current = workspaceManager.get_active_workspace_index();
        const next = Math.min(current + 1, workspaceManager.get_n_workspaces() - 1);
        this.switchWorkspace(next);
    }

    prevWorkspace() {
        const workspaceManager = global.workspace_manager;
        const current = workspaceManager.get_active_workspace_index();
        const prev = Math.max(current - 1, 0);
        this.switchWorkspace(prev);
    }

    getWorkspaceCount() {
        return global.workspace_manager.get_n_workspaces();
    }

    getCurrentWorkspace() {
        return global.workspace_manager.get_active_workspace_index();
    }
}

class ScreenshotManager {
    constructor() {
        this._cacheDir = GLib.get_home_dir() + '/.cache/EchoBase';
        this._path = this._cacheDir + '/screen.png';
        this._ensureCacheDir();
    }

    _ensureCacheDir() {
        const dir = Gio.File.new_for_path(this._cacheDir);
        if (!dir.query_exists(null)) {
            dir.make_directory_with_parents(null);
        }
    }

    takeScreenshotSync() {
        // Delete old file first
        try {
            Gio.File.new_for_path(this._path).delete(null);
        } catch (e) {}
        
        GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._captureViaScreenshotClass();
            return GLib.SOURCE_REMOVE;
        });
        
        return this._path;
    }
    
    async _captureViaScreenshotClass() {
        try {
            const screenshot = new Shell.Screenshot();
            
            // Get primary monitor dimensions
            const monitor = Main.layoutManager.primaryMonitor;
            const x = monitor.x;
            const y = monitor.y;
            const width = monitor.width;
            const height = monitor.height;
            
            log('EchoBase: capturing area ' + x + ',' + y + ' ' + width + 'x' + height);
            
            // Create output file stream
            const file = Gio.File.new_for_path(this._path);
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
            
            // GNOME 48: screenshot_area(x, y, width, height, stream, flash)
            const [content, scale] = await screenshot.screenshot_area(x, y, width, height, stream, false);
            
            stream.close(null);
            log('EchoBase: screenshot saved to ' + this._path);
            
        } catch (e) {
            log('EchoBase: capture error: ' + e.message);
            log('EchoBase: stack: ' + e.stack);
        }
    }
}

// Named keys the voice plugin can request by name.
const KEY_NAMES = {
    'enter': Clutter.KEY_Return, 'return': Clutter.KEY_Return,
    'tab': Clutter.KEY_Tab, 'backtab': Clutter.KEY_ISO_Left_Tab,
    'escape': Clutter.KEY_Escape, 'esc': Clutter.KEY_Escape,
    'space': Clutter.KEY_space, 'spacebar': Clutter.KEY_space,
    'backspace': Clutter.KEY_BackSpace, 'delete': Clutter.KEY_Delete,
    'up': Clutter.KEY_Up, 'down': Clutter.KEY_Down,
    'left': Clutter.KEY_Left, 'right': Clutter.KEY_Right,
    'home': Clutter.KEY_Home, 'end': Clutter.KEY_End,
    'pageup': Clutter.KEY_Page_Up, 'pagedown': Clutter.KEY_Page_Down,
    'super': Clutter.KEY_Super_L, 'menu': Clutter.KEY_Menu,
    'f5': Clutter.KEY_F5, 'f11': Clutter.KEY_F11,
};

// Modifier names -> modifier keyvals.
const MOD_KEYS = {
    'ctrl': Clutter.KEY_Control_L, 'control': Clutter.KEY_Control_L,
    'shift': Clutter.KEY_Shift_L,
    'alt': Clutter.KEY_Alt_L, 'option': Clutter.KEY_Alt_L,
    'super': Clutter.KEY_Super_L, 'meta': Clutter.KEY_Super_L, 'win': Clutter.KEY_Super_L,
};

// Numbered badges drawn over clickable UI elements (vimium-style hints).
class HintsOverlay {
    constructor() {
        this._container = null;
    }

    show(hintsJson) {
        this.hide();

        let hints = [];
        try {
            hints = JSON.parse(hintsJson);
        } catch (e) {
            hints = [];
        }
        if (!hints.length) return;

        const monitor = Main.layoutManager.primaryMonitor;
        this._container = new St.Widget({
            reactive: false,
            x: monitor.x, y: monitor.y,
            width: monitor.width, height: monitor.height,
        });

        for (const h of hints) {
            const badge = new St.Label({
                text: String(h.n),
                style: 'font-size: 15px; font-weight: 700; color: #0b1220; ' +
                    'background-color: rgba(250, 204, 21, 0.95); ' +
                    'border: 1px solid rgba(15, 23, 42, 0.6); ' +
                    'border-radius: 6px; padding: 0px 5px;',
            });
            badge.set_position(
                Math.round(h.x - monitor.x),
                Math.round(h.y - monitor.y)
            );
            this._container.add_child(badge);
        }

        Main.uiGroup.add_child(this._container);
    }

    hide() {
        if (this._container) {
            this._container.destroy();
            this._container = null;
        }
    }
}

// A centered panel listing open windows, numbered for voice selection.
class WindowPicker {
    constructor() {
        this._container = null;
    }

    show(itemsJson) {
        this.hide();

        let items = [];
        try {
            items = JSON.parse(itemsJson);
        } catch (e) {
            items = [];
        }
        if (!items.length) return;

        const monitor = Main.layoutManager.primaryMonitor;
        const panelW = Math.min(720, Math.floor(monitor.width * 0.6));
        const pad = 22, titleH = 40, rowH = 46;
        const h = titleH + pad * 2 + items.length * rowH;

        this._container = new St.Widget({
            reactive: false,
            x: monitor.x + Math.floor((monitor.width - panelW) / 2),
            y: monitor.y + Math.floor((monitor.height - h) / 2),
            width: panelW,
            height: h,
            style: 'background-color: rgba(15, 23, 42, 0.92); ' +
                'border: 1px solid rgba(147, 197, 253, 0.5); ' +
                'border-radius: 16px;',
        });

        const title = new St.Label({
            text: 'Say a number to switch window',
            style: 'font-size: 20px; font-weight: 600; color: #e0f2fe;',
        });
        title.set_position(pad, pad);
        this._container.add_child(title);

        items.forEach((label, i) => {
            const row = new St.Label({
                text: `${i + 1}.   ${label}`,
                style: 'font-size: 18px; color: #f0f9ff;',
            });
            row.set_position(pad + 4, titleH + pad + i * rowH);
            this._container.add_child(row);
        });

        Main.uiGroup.add_child(this._container);
    }

    hide() {
        if (this._container) {
            this._container.destroy();
            this._container = null;
        }
    }
}

// A small ring under the pointer that fills up as a dwell click approaches.
class DwellIndicator {
    constructor() {
        this._container = null;
        this._fill = null;
        this.R = 26;  // ring radius in px
    }

    show(x, y, fraction) {
        if (!this._container) {
            this._container = new St.Widget({
                reactive: false,
                width: this.R * 2,
                height: this.R * 2,
                style: `border: 2px solid rgba(56, 189, 248, 0.9); ` +
                    `border-radius: ${this.R}px; ` +
                    `background-color: rgba(15, 23, 42, 0.15);`,
            });
            this._fill = new St.Widget({
                reactive: false,
                style: 'background-color: rgba(56, 189, 248, 0.55); border-radius: 999px;',
            });
            this._container.add_child(this._fill);
            Main.uiGroup.add_child(this._container);
        }
        this._container.set_position(Math.round(x - this.R), Math.round(y - this.R));
        const f = Math.max(0, Math.min(1, fraction));
        const size = Math.round(this.R * 2 * f);
        this._fill.set_size(size, size);
        this._fill.set_position(this.R - Math.round(size / 2), this.R - Math.round(size / 2));
    }

    hide() {
        if (this._container) {
            this._container.destroy();
            this._container = null;
            this._fill = null;
        }
    }
}

class KeyboardController {
    constructor() {
        this._kbd = null;
    }

    _getKeyboard() {
        if (!this._kbd) {
            const seat = Clutter.get_default_backend().get_default_seat();
            this._kbd = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        }
        return this._kbd;
    }

    // Resolve a single token to a keyval: named key, modifier, or literal char.
    _keyval(token) {
        token = token.toLowerCase();
        if (token in KEY_NAMES) return KEY_NAMES[token];
        if (token in MOD_KEYS) return MOD_KEYS[token];
        if (token.length === 1) {
            const kv = Clutter['KEY_' + token];
            if (kv !== undefined) return kv;
        }
        return null;
    }

    _tap(keyval) {
        const kbd = this._getKeyboard();
        const t = GLib.get_monotonic_time();
        kbd.notify_keyval(t, keyval, Clutter.KeyState.PRESSED);
        kbd.notify_keyval(t + 8000, keyval, Clutter.KeyState.RELEASED);
    }

    pressKey(name) {
        const keyval = this._keyval(name.toLowerCase().replace(/[\s_]+/g, ''));
        if (keyval === null) {
            log('EchoBase: unknown key ' + name);
            return false;
        }
        this._tap(keyval);
        return true;
    }

    // combo like "ctrl+c", "ctrl+shift+t", "alt+tab". Last token is the key,
    // any leading tokens are modifiers held down around it.
    keyCombo(combo) {
        const parts = combo.toLowerCase().split('+').map(p => p.trim()).filter(p => p);
        if (parts.length === 0) return false;

        const keyToken = parts[parts.length - 1];
        const modTokens = parts.slice(0, -1);

        const keyval = this._keyval(keyToken);
        if (keyval === null) return false;

        const mods = [];
        for (const m of modTokens) {
            if (m in MOD_KEYS) mods.push(MOD_KEYS[m]);
            else return false;
        }

        const kbd = this._getKeyboard();
        let t = GLib.get_monotonic_time();
        // Press modifiers, tap key, release modifiers (reverse order).
        for (const mk of mods) {
            kbd.notify_keyval(t, mk, Clutter.KeyState.PRESSED);
            t += 4000;
        }
        kbd.notify_keyval(t, keyval, Clutter.KeyState.PRESSED);
        t += 8000;
        kbd.notify_keyval(t, keyval, Clutter.KeyState.RELEASED);
        t += 4000;
        for (const mk of mods.slice().reverse()) {
            kbd.notify_keyval(t, mk, Clutter.KeyState.RELEASED);
            t += 4000;
        }
        return true;
    }
}

export default class EchoBaseGridExtension {
    constructor() {
        this._dbus = null;
        this._grid = null;
        this._winMgr = null;
        this._screenMgr = null;
        this._kbd = null;
    }

    enable() {
        this._grid = new GridOverlay();
        this._winMgr = new WindowManager();
        this._screenMgr = new ScreenshotManager();
        this._kbd = new KeyboardController();
        this._dwell = new DwellIndicator();
        this._picker = new WindowPicker();
        this._hints = new HintsOverlay();

        this._dbus = Gio.DBusExportedObject.wrapJSObject(DBUS_INTERFACE, {
            // Grid
            Show: (width, height) => this._grid.show(width, height),
            Hide: () => this._grid.hide(),
            Update: (x, y, width, height) => this._grid.update(x, y, width, height),
            
            // Mouse
            Click: (x, y) => this._grid.click(x, y),
            DoubleClick: (x, y) => this._grid.doubleClick(x, y),
            TripleClick: (x, y) => this._grid.tripleClick(x, y),
            RightClick: (x, y) => this._grid.rightClick(x, y),
            MiddleClick: (x, y) => this._grid.middleClick(x, y),
            MoveTo: (x, y) => this._grid.moveTo(x, y),
            StartDrag: (x, y) => this._grid.startDrag(x, y),
            EndDrag: (x, y) => this._grid.endDrag(x, y),
            Scroll: (x, y, direction, clicks) => this._grid.scroll(x, y, direction, clicks),

            // Keyboard
            PressKey: (name) => this._kbd.pressKey(name),
            KeyCombo: (combo) => this._kbd.keyCombo(combo),

            // Dwell indicator
            ShowDwell: (x, y, fraction) => this._dwell.show(x, y, fraction),
            HideDwell: () => this._dwell.hide(),

            // Window picker overlay
            ShowWindowPicker: (itemsJson) => this._picker.show(itemsJson),
            HideWindowPicker: () => this._picker.hide(),

            // Native-element click hints
            ShowHints: (hintsJson) => this._hints.show(hintsJson),
            HideHints: () => this._hints.hide(),

            // Screenshot
            TakeScreenshot: () => this._screenMgr.takeScreenshotSync(),
            
            // Window management
            CloseWindow: () => this._winMgr.closeWindow(),
            MinimizeWindow: () => this._winMgr.minimizeWindow(),
            MaximizeWindow: () => this._winMgr.maximizeWindow(),
            UnmaximizeWindow: () => this._winMgr.unmaximizeWindow(),
            FullscreenWindow: () => this._winMgr.fullscreenWindow(),
            UnfullscreenWindow: () => this._winMgr.unfullscreenWindow(),
            TileLeft: () => this._winMgr.tileLeft(),
            TileRight: () => this._winMgr.tileRight(),
            
            // Window queries
            GetWindows: () => this._winMgr.getWindows(),
            FocusWindow: (title) => this._winMgr.focusWindow(title),
            
            // Workspaces
            SwitchWorkspace: (index) => this._winMgr.switchWorkspace(index),
            NextWorkspace: () => this._winMgr.nextWorkspace(),
            PrevWorkspace: () => this._winMgr.prevWorkspace(),
            GetWorkspaceCount: () => this._winMgr.getWorkspaceCount(),
            GetCurrentWorkspace: () => this._winMgr.getCurrentWorkspace(),
            
            // Screen info
            GetScreenSize: () => this._grid.getScreenSize(),
            GetMonitors: () => this._grid.getMonitors(),
        });

        this._dbus.export(Gio.DBus.session, '/org/EchoBase/Grid');
    }

    disable() {
        if (this._grid) {
            this._grid.hide();
            this._grid = null;
        }
        if (this._dwell) {
            this._dwell.hide();
            this._dwell = null;
        }
        if (this._picker) {
            this._picker.hide();
            this._picker = null;
        }
        if (this._hints) {
            this._hints.hide();
            this._hints = null;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
        this._winMgr = null;
        this._screenMgr = null;
        this._kbd = null;
    }
}
