// &#9472;&#9472; State &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
let selectedDevice = null;
let backupMode = 'auto';
let _backupPaused = false;
let _restorePaused = false;
let selectedRestoreDevice = null;
let selectedBackupPath = null;
let bkEventSource = null;
let rsEventSource = null;
let mirrorEventSource = null;
let syslogEventSource = null;
let allApps = [];
let syslogLines = [];

// &#9472;&#9472; Helpers &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function esc(str) {
  return String(str).replace(/[&<>"']/g, s =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[s]));
}

function getApiKey() {
  return localStorage.getItem('iphoneManagerApiKey') || '';
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = getApiKey();
  if (token) headers['X-API-Key'] = token;
  return headers;
}

function streamUrl(path) {
  const token = getApiKey();
  if (!token) return path;
  const join = path.includes('?') ? '&' : '?';
  return `${path}${join}api_key=${encodeURIComponent(token)}`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: authHeaders({ 'Content-Type': 'application/json', ...(opts.headers || {}) }),
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

function setBadge(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'badge ' + cls;
}

// &#9472;&#9472; Navigation &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function showSection(name) {
  document.querySelectorAll('.sec').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.navlink').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById('sec-' + name);
  if (sec) sec.classList.add('active');
  const lnk = document.querySelector(`.navlink[data-section="${name}"]`);
  if (lnk) lnk.classList.add('active');
  if (name === 'overview')    { if (!selectedDevice) showDevicePicker(); else showDeviceDetail(selectedDevice); }
  if (name === 'history')     loadHistory();
  if (name === 'apps')        loadApps();
  if (name === 'files')       afcRefresh();
  if (name === 'diagnostics') loadBattery();
  if (name === 'settings')    loadConfig();
  // Breadcrumb
  const labels = { overview:'Overview', backup:'Back Up', restore:'Restore', history:'History',
    apps:'Apps', files:'Files', mirror:'Screen Mirror', location:'Location',
    diagnostics:'Diagnostics', syslog:'Syslog', encryption:'Encryption', settings:'Settings' };
  const bc = document.getElementById('topbarBreadcrumb');
  const bl = document.getElementById('breadcrumbLabel');
  if (bc && bl) {
    if (name === 'overview') { bc.style.display = 'none'; }
    else { bl.textContent = labels[name] || name; bc.style.display = 'flex'; }
  }
}

// &#9472;&#9472; Device detection &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function detectDevice() {
  document.getElementById('topbarDevice').textContent = 'Scanning…';
  try {
    const data = await api('/api/devices');
    _applyDevices((data.devices || []).map(d => ({...d, _conn:'usb'})));
  } catch (e) { console.error('detectDevice error:', e); }
}

function _applyDevices(devices) {
  window._detectedDevices = devices;
  updateTopbar(devices);
  updateBackupDeviceList(devices);
  if (selectedDevice) {
    const still = devices.find(d => d.udid === selectedDevice.udid);
    if (still) { selectedDevice = still; updateSidebar([still]); }
    else selectedDevice = null;
  }
  renderDevicePicker(devices);
  if (!selectedDevice) showDevicePicker();
}

function updateTopbar(devices) {
  const chip = document.getElementById('deviceChip');
  const text = document.getElementById('chipText');
  if (!chip || !text) return;
  if (!devices.length) {
    chip.classList.remove('connected');
    text.textContent = 'No device connected';
    return;
  }
  const d = devices[0];
  chip.classList.add('connected');
  text.textContent = d.name + '  ·  ' + (d.model_name || d.product_type) + '  ·  iOS ' + d.ios_version;
}

function updateSidebar(devices) {
  const nameEl  = document.getElementById('deviceName');
  const subEl   = document.getElementById('deviceSub');
  const iosEl   = document.getElementById('deviceIos');
  const battRow = document.getElementById('batteryRow');
  if (!devices.length) {
    if (nameEl) nameEl.textContent = 'No Device';
    if (subEl)  subEl.textContent  = 'Connect via USB';
    if (iosEl)  iosEl.textContent  = '';
    if (battRow) battRow.style.display = 'none';
    return;
  }
  const d = devices[0];
  if (nameEl) nameEl.textContent = d.name;
  if (subEl)  subEl.textContent  = d.model_name || d.product_type;
  if (iosEl)  iosEl.textContent  = 'iOS ' + d.ios_version;
  if (d.battery_level != null && battRow) {
    battRow.style.display = 'flex';
    const fill = document.getElementById('batteryFill');
    const pct  = document.getElementById('batteryPct');
    if (fill) {
      fill.style.width      = d.battery_level + '%';
      fill.style.background = d.battery_level > 20 ? 'var(--green)' : 'var(--red)';
    }
    if (pct) pct.textContent = d.battery_level + '%' + (d.battery_charging ? ' ⚡' : '');
  }
  if (d.storage && d.storage.total_gb) {
    const s = d.storage;
    const el = document.getElementById('storageUsed');
    if (el) el.textContent = s.used_gb + ' / ' + s.total_gb + ' GB';
    const p = s.used_pct;
    ['stPhotos','stApps','stMessages','stOther'].forEach((id, idx) => {
      const el = document.getElementById(id);
      if (el) el.style.width = (p * [0.45,0.30,0.10,0.15][idx]) + '%';
    });
    const fr = document.getElementById('stFree');
    if (fr) fr.style.width = (100 - p) + '%';
  }
}

function renderDevicePicker(devices) {
  const grid = document.getElementById('devicePickerGrid');
  if (!grid) return;
  if (!devices.length) {
    grid.innerHTML = `<div class="device-picker-empty">
      <span>&#128241;</span>
      <p>No devices found. Connect your iPhone via USB or enable WiFi sync.</p>
      <button class="btn btn-primary" onclick="detectDevice()">&#128269; Scan Again</button>
    </div>`;
    return;
  }
  grid.innerHTML = devices.map((d, i) => {
    const batt = d.battery_level != null
      ? `<div class="dpc-batt">&#128267; ${d.battery_level}%${d.battery_charging ? ' &#9889;' : ''}</div>` : '';
    const isSelected = selectedDevice && selectedDevice.udid === d.udid;
    const conn = d._conn === 'wifi'
      ? '<span class="dpc-badge wifi">&#128246; WiFi</span>'
      : '<span class="dpc-badge">&#128268; USB</span>';
    return `<div class="device-picker-card${isSelected ? ' selected' : ''}" onclick="selectDevice(window._detectedDevices[${i}])">
      ${conn}
      <div class="dpc-icon">&#128241;</div>
      <div class="dpc-name">${esc(d.name)}</div>
      <div class="dpc-model">${esc(d.model_name || d.product_type)}</div>
      <div class="dpc-ios">iOS ${esc(d.ios_version)}</div>
      ${batt}
      <div class="dpc-actions">
        <button class="btn btn-primary btn-xs" onclick="event.stopPropagation();selectDevice(window._detectedDevices[${i}]);startBackup('${esc(d.udid)}','${esc(d.name)}')">&#128190; Back Up</button>
        <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation();selectDevice(window._detectedDevices[${i}]);showSection('diagnostics')">&#128267; Diag</button>
      </div>
    </div>`;
  }).join('');
}

function selectDevice(d) {
  selectedDevice = d;
  updateSidebar([d]);
  // Update picker highlight without touching display
  document.querySelectorAll('.device-picker-card').forEach((el, i) => {
    const dev = (window._detectedDevices || [])[i];
    el.classList.toggle('selected', dev && dev.udid === d.udid);
  });
  showDeviceDetail(d);
}

function showDeviceDetail(d) {
  const grid   = document.getElementById('devicePickerGrid');
  const detail = document.getElementById('overviewContent');
  const hdr    = document.querySelector('#sec-overview .sec-header');

  if (grid)   grid.style.display   = 'none';
  if (detail) detail.style.display = 'block';

  // Header: device name + back button
  if (hdr) {
    hdr.querySelector('h1').textContent = d.name;
    hdr.querySelector('p').textContent  = (d.model_name || d.product_type) + '  ·  iOS ' + d.ios_version;
    let back = document.getElementById('btnBackToPicker');
    if (!back) {
      back = document.createElement('button');
      back.id = 'btnBackToPicker';
      back.className = 'btn btn-ghost';
      back.innerHTML = '&#8592; All Devices';
      back.onclick = showDevicePicker;
      hdr.querySelector('.hdr-right').prepend(back);
    }
    back.style.display = 'inline-flex';
  }

  updateOverview(d);
  loadBackupSummary();
}

function showDevicePicker() {
  const grid   = document.getElementById('devicePickerGrid');
  const detail = document.getElementById('overviewContent');
  if (grid)   grid.style.display   = '';
  if (detail) detail.style.display = 'none';
  const hdr = document.querySelector('#sec-overview .sec-header');
  if (hdr) {
    hdr.querySelector('h1').textContent = 'Devices';
    hdr.querySelector('p').textContent  = 'Select a device to manage';
    const back = document.getElementById('btnBackToPicker');
    if (back) back.style.display = 'none';
  }
}

// &#9472;&#9472; Overview &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function updateOverview(d) {
  const el = document.getElementById('overviewContent');
  const s  = d.storage || {};
  const battColor = (d.battery_level || 0) > 20 ? '#16a34a' : '#dc2626';
  el.innerHTML = `
    <div class="ov-grid">
      <div class="ov-tile"><span class="ot-icon">&#128241;</span><div class="ot-label">Device Name</div><div class="ot-val sm">${esc(d.name)}</div></div>
      <div class="ov-tile"><span class="ot-icon">&#127759;</span><div class="ot-label">iOS Version</div><div class="ot-val">${esc(d.ios_version)} <span style="font-size:12px;color:var(--muted)">(${esc(d.build||'')})</span></div></div>
      <div class="ov-tile"><span class="ot-icon">&#128187;</span><div class="ot-label">Model</div><div class="ot-val sm">${esc(d.model_name || d.product_type)}</div></div>
      <div class="ov-tile"><span class="ot-icon">&#128267;</span><div class="ot-label">Battery</div><div class="ot-val" style="color:${battColor}">${d.battery_level !== null ? d.battery_level + '%' + (d.battery_charging ? ' &#9889;' : '') : '&#8212;'}</div></div>
      <div class="ov-tile"><span class="ot-icon">&#128190;</span><div class="ot-label">Storage</div><div class="ot-val sm">${s.used_gb || '&#8212;'} / ${s.total_gb || '&#8212;'} GB <span style="color:var(--muted);font-size:11px">(${s.free_gb||0} GB free)</span></div></div>
      <div class="ov-tile"><span class="ot-icon">&#128246;</span><div class="ot-label">Serial Number</div><div class="ot-val sm">${esc(d.serial || '&#8212;')}</div></div>
      <div class="ov-tile"><span class="ot-icon">&#128225;</span><div class="ot-label">Wi-Fi MAC</div><div class="ot-val sm">${esc(d.wifi_mac || '&#8212;')}</div></div>
      <div class="ov-tile"><span class="ot-icon">&#128309;</span><div class="ot-label">Bluetooth MAC</div><div class="ot-val sm">${esc(d.bt_mac || '&#8212;')}</div></div>
    </div>
    <div id="overviewBackupSummary"></div>`;
  loadBackupSummaryInline();
}

async function loadBackupSummary() {
  try {
    const data = await api('/api/backups');
    if (data.backups && data.backups.length) {
      const last = data.backups[0];
      document.getElementById('rpLast').innerHTML =
        `<span class="muted small">Last backup:<br><strong>${last.modified.replace('T',' ')}</strong><br>${last.size_gb != null ? last.size_gb + ' GB' : 'size n/a'}</span>`;
    }
  } catch (_) {}
}

async function loadBackupSummaryInline() {
  try {
    const data = await api('/api/backups');
    const el = document.getElementById('overviewBackupSummary');
    if (!el) return;
    if (!data.backups || !data.backups.length) {
      el.innerHTML = `<div class="card" style="border-left:3px solid var(--orange)">
        <div class="card-hdr"><h2>&#128190; No Backups Yet</h2></div>
        <p class="small muted">No backups found on NAS. Click Back Up Now to create your first backup.</p>
        <button class="btn btn-primary" style="margin-top:10px" onclick="showSection('backup'); detectDevice()">&#128190; Back Up Now</button>
      </div>`;
      return;
    }
    const last = data.backups[0];
    document.getElementById('rpLast').innerHTML =
      `<span class="muted small">Last backup:<br><strong>${last.modified.replace('T',' ')}</strong><br>${last.size_gb != null ? last.size_gb + ' GB' : 'size n/a'}</span>`;
    el.innerHTML = `
      <div class="card" style="border-left:3px solid var(--green)">
        <div class="card-hdr">
          <div><h2>&#128190; Last Backup</h2><p>${last.modified.replace('T',' ')}</p></div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" onclick="showSection('history')">&#128450; History</button>
            <button class="btn btn-primary btn-sm" onclick="showSection('backup'); detectDevice()">&#128190; Back Up</button>
          </div>
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
          <div><div class="ot-label">Size</div><div class="ot-val">${last.size_gb != null ? last.size_gb + ' GB' : 'n/a'}</div></div>
          <div><div class="ot-label">Location</div><div class="ot-val sm" style="font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(last.path)}</div></div>
          <div><div class="ot-label">Total Backups</div><div class="ot-val">${data.backups.length}</div></div>
        </div>
      </div>`;
  } catch (_) {}
}

// &#9472;&#9472; Backup device list &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function updateBackupDeviceList(devices) {
  const el = document.getElementById('backupDeviceList');
  if (!devices.length) { el.innerHTML = "<p class='muted'>No device detected.</p>"; return; }
  el.innerHTML = devices.map((d, i) => `
    <div class="dev-row ${selectedDevice?.udid === d.udid ? 'sel' : ''}" onclick="selectBackupDevice(${i})">
      <div class="dev-icon">&#128241;</div>
      <div class="dev-info">
        <strong>${esc(d.name)}</strong>
        <span>${esc(d.model_name || d.product_type)} &#183; iOS ${esc(d.ios_version)}</span>
        <span class="udid-text">${esc(d.udid)}</span>
      </div>
      <button class="btn btn-primary btn-sm" onclick="event.stopPropagation();startBackup('${esc(d.udid)}','${esc(d.name)}')">Back Up</button>
    </div>`).join('');
}

function selectBackupDevice(i) {
  selectedDevice = (window._detectedDevices || [])[i] || selectedDevice;
}

function onModeChange() {
  backupMode = document.querySelector('input[name="bkMode"]:checked').value;
  const hints = {
    auto: 'First run = full, then incremental',
    incremental: 'Only changed files transferred (faster)',
    full: 'All files transferred every time',
  };
  document.getElementById('modeHint').textContent = hints[backupMode];
}

// &#9472;&#9472; Backup &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function startBackup(udid, name) {
  if (!confirm(`Start backup of ${name}?`)) return;
  showSection('backup');
  const card = document.getElementById('bkProgressCard');
  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth' });
  _resetBkProgress();
  try {
    await api('/api/backup', { method: 'POST', body: JSON.stringify({
      udid, device_name: name,
      full: backupMode === 'full',
      incremental: backupMode === 'incremental',
      wifi: wifiBackupMode,
    })});
    _startBkStream();
  } catch (e) {
    setBadge('bkBadge', 'Failed', 'badge-err');
    document.getElementById('bkFile').textContent = JSON.stringify(e);
  }
}

function _resetBkProgress() {
  document.getElementById('bkFill').style.width = '0%';
  document.getElementById('bkPct').textContent  = '0%';
  document.getElementById('bkFile').textContent = 'Starting&#8230;';
  setBadge('bkBadge', 'Running', 'badge-run');
  document.getElementById('bkLog').innerHTML = '';
  ['Photos','Apps','Messages','Contacts','Health','Notes','Calendar','Safari','Settings','Mail','Other'].forEach(c => {
    document.getElementById('cv-' + c).textContent = '0';
    document.getElementById('cb-' + c).style.width = '0%';
  });
}

function _startBkStream() {
  if (bkEventSource) bkEventSource.close();
  bkEventSource = new EventSource(streamUrl('/api/backup/stream'));
  bkEventSource.onmessage = e => {
    const s = JSON.parse(e.data);
    _updateBkUI(s);
    if (s.done) {
      bkEventSource.close();
      setBadge('bkBadge', s.ok ? 'Complete &#10003;' : 'Failed', s.ok ? 'badge-done' : 'badge-err');
      if (s.ok) { document.getElementById('bkFile').textContent = 'Saved to: ' + s.destination; loadBackupSummary(); }
      else document.getElementById('bkFile').textContent = s.error || 'Backup failed';
    }
  };
  bkEventSource.onerror = () => { bkEventSource.close(); _pollBk(); };
}

function _pollBk() {
  const iv = setInterval(async () => {
    try { const s = await api('/api/backup/progress'); _updateBkUI(s); if (s.done) clearInterval(iv); } catch (_) {}
  }, 1500);
}

function _updateBkUI(s) {
  document.getElementById('bkFill').style.width = (s.percent || 0) + '%';
  document.getElementById('bkPct').textContent  = (s.percent || 0) + '%';
  if (s.files_sent || s.total_files) {
    const sent  = s.files_sent  || 0;
    const total = s.total_files || 0;
    document.getElementById('bkFileCount').textContent =
      total > 0 ? `${sent.toLocaleString()} of ${total.toLocaleString()} files` : `${sent.toLocaleString()} files processed`;
  }
  if (s.current_file) document.getElementById('bkFile').textContent = s.current_file;
  _backupPaused = s.paused || false;
  const pb = document.getElementById('btnBkPause');
  if (pb) { pb.textContent = _backupPaused ? '&#9654; Resume' : '&#9208; Pause'; pb.className = _backupPaused ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-warn'; }
  if (s.paused)       setBadge('bkBadge', 'Paused',  'badge-paused');
  else if (s.running) setBadge('bkBadge', (s.mode || 'Full') + ' &#8212; Running', 'badge-run');
  const cats = s.categories || {}, tot = Object.values(cats).reduce((a,b)=>a+b,0)||1;
  Object.entries(cats).forEach(([c, n]) => {
    document.getElementById('cv-' + c).textContent = n;
    document.getElementById('cb-' + c).style.width = Math.round(n/tot*100) + '%';
  });
  const log = document.getElementById('bkLog');
  log.innerHTML = (s.log||[]).slice(-60).map(l=>`<div class="log-line">${esc(l)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}

async function stopBackup()        { if (confirm('Stop backup?')) await api('/api/backup/stop',   {method:'POST'}); }
async function pauseResumeBackup() { await api(_backupPaused ? '/api/backup/resume' : '/api/backup/pause', {method:'POST'}); }

// &#9472;&#9472; Restore &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function loadRestoreDevices() {
  const el = document.getElementById('restoreDeviceList');
  el.innerHTML = "<p class='muted'>Scanning&#8230;</p>";
  try {
    const data = await api('/api/devices');
    const devices = data.devices || [];
    window._restoreDevices = devices;
    if (!devices.length) { el.innerHTML = "<p class='muted'>No device detected.</p>"; return; }
    el.innerHTML = devices.map((d,i) => `
      <div class="dev-row ${selectedRestoreDevice?.udid===d.udid?'sel':''}" onclick="selectRestoreDevice(${i})">
        <div class="dev-icon">&#128241;</div>
        <div class="dev-info"><strong>${esc(d.name)}</strong><span>${esc(d.model_name||d.product_type)} &#183; iOS ${esc(d.ios_version)}</span></div>
        <span class="badge ${selectedRestoreDevice?.udid===d.udid?'badge-done':'badge-run'}">${selectedRestoreDevice?.udid===d.udid?'Selected &#10003;':'Select'}</span>
      </div>`).join('');
    if (!selectedRestoreDevice) selectRestoreDevice(0);
  } catch (e) { el.innerHTML = `<pre>${JSON.stringify(e,null,2)}</pre>`; }
}

function selectRestoreDevice(i) { selectedRestoreDevice = (window._restoreDevices||[])[i]; loadRestoreDevices(); }

async function loadRestoreBackups() {
  const el = document.getElementById('restoreBackupList');
  el.innerHTML = "<p class='muted'>Loading&#8230;</p>";
  try {
    const data = await api('/api/backups');
    if (!data.backups.length) { el.innerHTML = "<p class='muted'>No backups found.</p>"; return; }
    el.innerHTML = data.backups.map(b => `
      <div class="rs-bk-row ${selectedBackupPath===b.path?'sel':''}" onclick="selectRestoreBk('${esc(b.path)}')">
        <div class="dev-icon">&#128190;</div>
        <div class="dev-info"><strong>${esc(b.name)}</strong><span>${b.modified}</span></div>
        <span style="font-weight:700;color:var(--orange)">${b.size_gb != null ? b.size_gb + ' GB' : 'n/a'}</span>
        ${selectedBackupPath===b.path?'<span class="badge badge-done">&#10003;</span>':''}
      </div>`).join('');
  } catch (e) { el.innerHTML = `<pre>${JSON.stringify(e,null,2)}</pre>`; }
}

function selectRestoreBk(path) { selectedBackupPath = path; loadRestoreBackups(); }

async function startRestore() {
  if (!selectedRestoreDevice) { alert('Select a target device.'); return; }
  if (!selectedBackupPath)    { alert('Select a backup.'); return; }
  if (!confirm(`&#9888;&#65039; ERASE and restore ${selectedRestoreDevice.name}?`)) return;
  const card = document.getElementById('rsProgressCard');
  card.style.display = 'block'; card.scrollIntoView({behavior:'smooth'});
  document.getElementById('rsFill').style.width = '0%';
  document.getElementById('rsPct').textContent  = '0%';
  document.getElementById('rsFile').textContent = 'Starting&#8230;';
  setBadge('rsBadge','Running','badge-run');
  document.getElementById('rsLog').innerHTML = '';
  try {
    await api('/api/restore', {method:'POST', body: JSON.stringify({
      udid: selectedRestoreDevice.udid, backup_path: selectedBackupPath,
      password: document.getElementById('restorePwd').value,
    })});
    _startRsStream();
  } catch (e) { setBadge('rsBadge','Failed','badge-err'); document.getElementById('rsFile').textContent = JSON.stringify(e); }
}

function _startRsStream() {
  if (rsEventSource) rsEventSource.close();
  rsEventSource = new EventSource(streamUrl('/api/restore/stream'));
  rsEventSource.onmessage = e => {
    const s = JSON.parse(e.data);
    document.getElementById('rsFill').style.width = (s.percent||0) + '%';
    document.getElementById('rsPct').textContent  = (s.percent||0) + '%';
    if (s.current_file) document.getElementById('rsFile').textContent = s.current_file;
    _restorePaused = s.paused || false;
    const pb = document.getElementById('btnRsPause');
    if (pb) { pb.textContent = _restorePaused ? '&#9654; Resume' : '&#9208; Pause'; pb.className = _restorePaused ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-warn'; }
    if (s.paused) setBadge('rsBadge','Paused','badge-paused');
    const log = document.getElementById('rsLog');
    log.innerHTML = (s.log||[]).slice(-60).map(l=>`<div class="log-line">${esc(l)}</div>`).join('');
    log.scrollTop = log.scrollHeight;
    if (s.done) {
      rsEventSource.close();
      setBadge('rsBadge', s.ok?'Complete &#10003;':'Failed', s.ok?'badge-done':'badge-err');
      document.getElementById('rsFile').textContent = s.ok ? 'Restore complete. Device will reboot.' : (s.error||'Failed');
    }
  };
}

async function stopRestore()        { if (confirm('Stop restore?')) await api('/api/restore/stop',   {method:'POST'}); }
async function pauseResumeRestore() { await api(_restorePaused ? '/api/restore/resume' : '/api/restore/pause', {method:'POST'}); }

// &#9472;&#9472; History &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function loadHistory() {
  const el = document.getElementById('historyList');
  el.innerHTML = "<p class='muted'>Loading&#8230;</p>";
  try {
    const data = await api('/api/backups');
    if (!data.backups.length) { el.innerHTML = "<p class='muted'>No backups yet.</p>"; return; }
    el.innerHTML = data.backups.map((b, i) => `
      <div class="hist-row" onclick="openDetail(${i})" style="cursor:pointer" data-path="${esc(b.path)}" data-name="${esc(b.name)}">
        <div class="hist-icon">&#128190;</div>
        <div class="hist-info">
          <strong>${esc(b.name)}</strong>
          <span>${b.modified}</span>
          <span class="muted" style="font-size:10px">${esc(b.path)}</span>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
          <span class="hist-size">${b.size_gb != null ? b.size_gb + ' GB' : ''}</span>
          <span class="btn btn-sm btn-ghost">&#128269; View Contents</span>
        </div>
      </div>`).join('');
    window._backupList = data.backups;
  } catch (e) { el.innerHTML = `<pre>${JSON.stringify(e,null,2)}</pre>`; }
}

let _detailData = null;
let _activeCategory = null;

async function openDetail(idx) {
  const b = (window._backupList || [])[idx];
  if (!b) return;
  const path = b.path;
  const name = b.name;
  document.getElementById('detailModal').style.display = 'flex';
  document.getElementById('detailTitle').textContent = name;
  document.getElementById('detailDevice').innerHTML = "<p class='muted' style='padding:8px'>Loading&#8230;</p>";
  document.getElementById('detailCats').innerHTML = '';
  document.getElementById('detailFiles').innerHTML = '';
  _detailData = null; _activeCategory = null;

  try {
    const data = await api('/api/backups/detail?path=' + encodeURIComponent(path));
    _detailData = data;

    // Device info tiles
    const d = data.device || {};
    document.getElementById('detailDevice').innerHTML = [
      ['&#128241; Device',   d.name],
      ['&#128230; Model',    d.product],
      ['&#127759; iOS',      d.ios_version],
      ['&#128290; Serial',   d.serial],
      ['&#128197; Date',     (d.backup_date||'').replace('T',' ').slice(0,19)],
      ['&#128194; Files',    (data.total_files||0).toLocaleString()],
      ['&#128274; Encrypted', d.encrypted ? 'Yes &#10003;' : 'No'],
    ].filter(([,v])=>v).map(([l,v]) =>
      `<div class="dd-item"><div class="dd-label">${l}</div><div class="dd-val">${esc(String(v))}</div></div>`
    ).join('');

    // Category chips
    const catIcons = {Photos:'&#128444;',Apps:'&#128230;',Messages:'&#128172;',Contacts:'&#128100;',
                      Health:'&#10084;&#65039;',Notes:'&#128221;',Calendar:'&#128197;',Safari:'&#127760;',
                      Settings:'&#9881;&#65039;',Mail:'&#9993;&#65039;',Other:'&#128193;'};
    const cats = data.categories || {};
    document.getElementById('detailCats').innerHTML =
      Object.entries(cats).filter(([,n])=>n>0)
        .sort((a,b)=>b[1]-a[1])
        .map(([cat,n]) =>
          `<div class="dc-chip" onclick="filterDetail('${cat}')">
            <span>${catIcons[cat]||'&#128193;'}</span>
            <span>${cat}</span>
            <span class="dc-count">${n.toLocaleString()}</span>
          </div>`
        ).join('');

    renderDetailFiles(null);
  } catch (e) {
    document.getElementById('detailDevice').innerHTML = `<p class='muted' style='padding:8px'>${JSON.stringify(e)}</p>`;
  }
}

function filterDetail(cat) {
  _activeCategory = _activeCategory === cat ? null : cat;
  document.querySelectorAll('.dc-chip').forEach(c => {
    c.classList.toggle('active', _activeCategory && c.textContent.includes(cat) && _activeCategory === cat);
  });
  renderDetailFiles(_activeCategory);
}

function renderDetailFiles(cat) {
  if (!_detailData) return;
  const el = document.getElementById('detailFiles');
  const bycat = _detailData.files_by_category || {};
  let files = [];
  if (cat) {
    files = bycat[cat] || [];
  } else {
    Object.values(bycat).forEach(arr => files.push(...arr));
    files = files.slice(0, 300);
  }
  if (!files.length) { el.innerHTML = "<p class='muted' style='padding:12px 0'>No files in this category.</p>"; return; }
  el.className = 'detail-files';
  el.innerHTML = `<p class="small muted" style="margin-bottom:8px">Showing ${files.length.toLocaleString()} files${cat ? ' in ' + cat : ''}</p>` +
    files.map(f =>
      `<div class="df-row"><span class="df-domain">${esc(f.domain)}</span><span class="df-path">${esc(f.path)}</span></div>`
    ).join('');
}

function closeDetail(e) {
  if (e.target.id === 'detailModal') document.getElementById('detailModal').style.display = 'none';
}

// &#9472;&#9472; Apps &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function loadApps() {
  if (!selectedDevice) { document.getElementById('appList').innerHTML = "<p class='muted'>No device connected.</p>"; return; }
  document.getElementById('appList').innerHTML = "<p class='muted'>Loading apps&#8230;</p>";
  try {
    const data = await api(`/api/apps/${selectedDevice.udid}`);
    allApps = data.apps || [];
    renderApps(allApps);
  } catch (e) { document.getElementById('appList').innerHTML = `<pre>${JSON.stringify(e,null,2)}</pre>`; }
}

function renderApps(apps) {
  const el = document.getElementById('appList');
  if (!apps.length) { el.innerHTML = "<p class='muted'>No apps found.</p>"; return; }
  el.innerHTML = `<div class="app-list-wrap">${apps.map(a => `
    <div class="app-row">
      <div class="app-icon">&#128230;</div>
      <div class="app-info"><strong>${esc(a.name)}</strong><span>${esc(a.bundle_id)} &#183; v${esc(a.version)}</span></div>
      <button class="btn btn-sm btn-danger" onclick="uninstallApp('${esc(a.bundle_id)}','${esc(a.name)}')">Uninstall</button>
    </div>`).join('')}</div>`;
}

function filterApps() {
  const q = document.getElementById('appSearch').value.toLowerCase();
  renderApps(allApps.filter(a => a.name.toLowerCase().includes(q) || a.bundle_id.toLowerCase().includes(q)));
}

async function uninstallApp(bundleId, name) {
  if (!confirm(`Uninstall ${name}?`)) return;
  try {
    const r = await api(`/api/apps/${selectedDevice.udid}/uninstall`, {method:'POST', body: JSON.stringify({bundle_id: bundleId})});
    alert(r.ok ? `${name} uninstalled.` : `Failed: ${r.message}`);
    if (r.ok) loadApps();
  } catch (e) { alert('Error: ' + JSON.stringify(e)); }
}

// &#9472;&#9472; Screen Mirror &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function startMirror() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  // Update both button sets
  ['btnMirrorStart','btnMirrorStart2'].forEach(id => { const el = document.getElementById(id); if(el) el.style.display='none'; });
  ['btnMirrorStop','btnMirrorStop2'].forEach(id => { const el = document.getElementById(id); if(el) el.style.display='inline-block'; });
  document.getElementById('mirrorPlaceholder').style.display = 'none';
  document.getElementById('mirrorImg').style.display = 'block';
  const errEl = document.getElementById('mirrorError'); if(errEl) errEl.textContent = '';
  const statusEl = document.getElementById('mirrorStatus'); if(statusEl) statusEl.textContent = 'Running';
  const devEl = document.getElementById('mirrorDevice'); if(devEl) devEl.textContent = selectedDevice.name;
  await api(`/api/mirror/${selectedDevice.udid}/start`, {method:'POST'});
  if (mirrorEventSource) mirrorEventSource.close();
  mirrorEventSource = new EventSource(streamUrl('/api/mirror/stream'));
  mirrorEventSource.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.frame) document.getElementById('mirrorImg').src = 'data:image/png;base64,' + d.frame;
    if (d.fps) {
      const f1 = document.getElementById('mirrorFps');  if(f1) f1.textContent = d.fps.toFixed(1) + ' fps';
      const f2 = document.getElementById('mirrorFps2'); if(f2) f2.textContent = d.fps.toFixed(1) + ' fps';
    }
    if (d.error) { const el = document.getElementById('mirrorError'); if(el) el.textContent = d.error; }
  };
}

async function stopMirror() {
  if (mirrorEventSource) { mirrorEventSource.close(); mirrorEventSource = null; }
  await api('/api/mirror/stop', {method:'POST'});
  ['btnMirrorStart','btnMirrorStart2'].forEach(id => { const el = document.getElementById(id); if(el) el.style.display='inline-block'; });
  ['btnMirrorStop','btnMirrorStop2'].forEach(id => { const el = document.getElementById(id); if(el) el.style.display='none'; });
  document.getElementById('mirrorPlaceholder').style.display = 'block';
  document.getElementById('mirrorImg').style.display = 'none';
  const f1 = document.getElementById('mirrorFps');  if(f1) f1.textContent = '';
  const f2 = document.getElementById('mirrorFps2'); if(f2) f2.textContent = '&mdash;';
  const statusEl = document.getElementById('mirrorStatus'); if(statusEl) statusEl.textContent = 'Stopped';
}

// &#9472;&#9472; Diagnostics &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function loadBattery() {
  if (!selectedDevice) return;
  const el = document.getElementById('batteryInfo');
  el.innerHTML = "<p class='muted'>Loading&#8230;</p>";
  try {
    const data = await api(`/api/diagnostics/${selectedDevice.udid}/battery`);
    const b = data.battery || {};
    el.innerHTML = Object.entries(b).map(([k,v]) =>
      `<div class="batt-stat"><span>${esc(k)}</span><span class="batt-val">${esc(String(v))}</span></div>`
    ).join('') || "<p class='muted'>No data</p>";
  } catch (e) { el.innerHTML = `<p class='muted'>${JSON.stringify(e)}</p>`; }
}

async function loadCrashes() {
  if (!selectedDevice) return;
  const el = document.getElementById('crashList');
  el.innerHTML = "<p class='muted'>Fetching&#8230;</p>";
  try {
    const data = await api(`/api/diagnostics/${selectedDevice.udid}/crashes`);
    const reports = data.reports || [];
    el.innerHTML = reports.length
      ? reports.map(r => `<div class="batt-stat"><span>${esc(r.name)}</span><span class="batt-val">${r.size_kb} KB</span></div>`).join('')
      : "<p class='muted'>No crash reports.</p>";
  } catch (e) { el.innerHTML = `<p class='muted'>${JSON.stringify(e)}</p>`; }
}

async function loadSleepLog() {
  if (!selectedDevice) return;
  document.getElementById('sleepLog').textContent = 'Fetching&#8230;';
  try {
    const data = await api(`/api/diagnostics/${selectedDevice.udid}/sleep`);
    document.getElementById('sleepLog').textContent = data.log || 'No data';
  } catch (e) { document.getElementById('sleepLog').textContent = JSON.stringify(e); }
}

async function restartDevice() {
  if (!selectedDevice || !confirm('Restart device?')) return;
  const r = await api(`/api/diagnostics/${selectedDevice.udid}/restart`, {method:'POST'});
  document.getElementById('diagMsg').textContent = r.message || 'Restarting&#8230;';
}

async function shutdownDevice() {
  if (!selectedDevice || !confirm('Shutdown device?')) return;
  const r = await api(`/api/diagnostics/${selectedDevice.udid}/shutdown`, {method:'POST'});
  document.getElementById('diagMsg').textContent = r.message || 'Shutting down&#8230;';
}

// &#9472;&#9472; Syslog &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function startSyslog() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  document.getElementById('btnSysStart').style.display = 'none';
  document.getElementById('btnSysStop').style.display  = 'inline-block';
  await api(`/api/syslog/${selectedDevice.udid}/start`, {method:'POST'});
  if (syslogEventSource) syslogEventSource.close();
  syslogEventSource = new EventSource(streamUrl('/api/syslog/stream'));
  syslogEventSource.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.heartbeat) return;
    syslogLines.push(d.line || '');
    if (syslogLines.length > 1000) syslogLines.shift();
    _renderSyslog();
  };
}

async function stopSyslog() {
  if (syslogEventSource) { syslogEventSource.close(); syslogEventSource = null; }
  await api('/api/syslog/stop', {method:'POST'});
  document.getElementById('btnSysStart').style.display = 'inline-block';
  document.getElementById('btnSysStop').style.display  = 'none';
}

function clearSyslog() { syslogLines = []; _renderSyslog(); }

function filterSyslog() { _renderSyslog(); }

function _renderSyslog() {
  const q   = (document.getElementById('syslogFilter').value || '').toLowerCase();
  const box = document.getElementById('syslogBox');
  const lines = q ? syslogLines.filter(l => l.toLowerCase().includes(q)) : syslogLines;
  box.innerHTML = lines.slice(-200).map(l => {
    const cls = l.includes('error') || l.includes('Error') ? 'log-err'
              : l.includes('warn')  || l.includes('Warn')  ? 'log-warn' : '';
    return `<div class="log-line ${cls}">${esc(l)}</div>`;
  }).join('');
  box.scrollTop = box.scrollHeight;
}

// &#9472;&#9472; Encryption &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function enableEncryption() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  const pwd = document.getElementById('encPwd').value;
  if (!pwd) { alert('Enter a password.'); return; }
  const out = document.getElementById('encOutput');
  out.style.display = 'block'; out.textContent = 'Enabling&#8230;';
  try {
    const r = await api('/api/encryption', {method:'POST', body: JSON.stringify({udid: selectedDevice.udid, password: pwd})});
    out.textContent = JSON.stringify(r, null, 2);
  } catch (e) { out.textContent = JSON.stringify(e, null, 2); }
}

// &#9472;&#9472; Settings &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function runHealthCheck() {
  const el = document.getElementById('healthOut');
  el.textContent = 'Checking&#8230;';
  try {
    const data = await api('/api/health');
    el.textContent = JSON.stringify(data, null, 2);
  } catch (e) { el.textContent = JSON.stringify(e, null, 2); }
}

// &#9472;&#9472; Quick actions &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
function quickTransfer() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  backupMode = 'incremental';
  document.querySelector('input[name="bkMode"][value="incremental"]').checked = true;
  onModeChange();
  showSection('backup');
  startBackup(selectedDevice.udid, selectedDevice.name);
}

// &#9472;&#9472; Init &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
document.addEventListener('DOMContentLoaded', async () => {
  const ready = await ensureSetupComplete();
  if (!ready) return;

  detectDevice();

  // Reconnect to in-progress backup or restore
  (async () => {
    try {
      const bk = await api('/api/backup/progress');
      if (bk.running || (bk.done === false && bk.percent > 0)) {
        showSection('backup');
        const card = document.getElementById('bkProgressCard');
        card.style.display = 'block';
        _updateBkUI(bk);
        if (!bk.done) _startBkStream();
      }
    } catch (_) {}

    try {
      const rs = await api('/api/restore/progress');
      if (rs.running || (rs.done === false && rs.percent > 0)) {
        showSection('restore');
        const card = document.getElementById('rsProgressCard');
        card.style.display = 'block';
        document.getElementById('rsFill').style.width  = (rs.percent || 0) + '%';
        document.getElementById('rsPct').textContent   = (rs.percent || 0) + '%';
        document.getElementById('rsFile').textContent  = rs.current_file || 'In progress&#8230;';
        setBadge('rsBadge', rs.paused ? 'Paused' : 'Running', rs.paused ? 'badge-paused' : 'badge-run');
        if (!rs.done) _startRsStream();
      }
    } catch (_) {}
  })();
});

// &#9472;&#9472; AFC File Browser &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
let _afcPath = '/';

async function afcRefresh() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  const el = document.getElementById('fileList');
  el.innerHTML = "<p class='muted'>Loading&#8230;</p>";
  document.getElementById('filePath').textContent = _afcPath;
  try {
    const data = await api(`/api/afc/${selectedDevice.udid}/list?path=${encodeURIComponent(_afcPath)}`);
    if (!data.ok) { el.innerHTML = `<p class='muted'>${esc(data.error || 'Failed')}</p>`; return; }
    const items = data.items || [];
    if (!items.length) { el.innerHTML = "<p class='muted'>Empty folder.</p>"; return; }
    el.innerHTML = `<div class="app-list-wrap">${items.map(item => {
      const isDir = !item.includes('.');
      const fullPath = _afcPath.replace(/\/$/, '') + '/' + item;
      return `<div class="app-row" style="cursor:pointer" onclick="afcNavigate('${esc(fullPath)}','${esc(item)}')">
        <div class="app-icon">${isDir ? '&#128193;' : '&#128196;'}</div>
        <div class="app-info"><strong>${esc(item)}</strong><span>${esc(fullPath)}</span></div>
        ${!isDir ? `<button class="btn btn-sm btn-ghost" onclick="event.stopPropagation()">&#11015; Download</button>` : ''}
      </div>`;
    }).join('')}</div>`;
  } catch (e) { el.innerHTML = `<pre>${JSON.stringify(e,null,2)}</pre>`; }
}

function afcNavigate(path, name) {
  _afcPath = path;
  afcRefresh();
}

function afcUp() {
  const parts = _afcPath.split('/').filter(Boolean);
  parts.pop();
  _afcPath = '/' + parts.join('/');
  if (!_afcPath) _afcPath = '/';
  afcRefresh();
}

// &#9472;&#9472; Location Spoof &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function setLocation() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  const lat = parseFloat(document.getElementById('locLat').value);
  const lon = parseFloat(document.getElementById('locLon').value);
  if (isNaN(lat) || isNaN(lon)) { alert('Enter valid latitude and longitude.'); return; }
  const r = await api(`/api/location/${selectedDevice.udid}/set`, {
    method: 'POST', body: JSON.stringify({ lat, lon }),
  });
  document.getElementById('locMsg').textContent = r.ok
    ? `&#9989; Location set to ${lat}, ${lon}`
    : `&#10060; ${r.message}`;
}

async function resetLocation() {
  if (!selectedDevice) return;
  const r = await api(`/api/location/${selectedDevice.udid}/stop`, { method: 'POST' });
  document.getElementById('locMsg').textContent = r.ok ? '&#9989; Location reset to real GPS' : `&#10060; ${r.message}`;
}

function quickLoc(lat, lon) {
  document.getElementById('locLat').value = lat;
  document.getElementById('locLon').value = lon;
  setLocation();
}

// &#9472;&#9472; Developer Mode &#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;
async function checkDevMode() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  const r = await api(`/api/developer/${selectedDevice.udid}/status`);
  document.getElementById('devModeMsg').textContent =
    `Developer Mode: ${r.enabled ? '&#9989; Enabled' : '&#10060; Disabled'} &#8212; ${r.raw || ''}`;
}

async function enableDevMode() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  document.getElementById('devModeMsg').textContent = 'Enabling&#8230;';
  const r = await api(`/api/developer/${selectedDevice.udid}/enable`, { method: 'POST' });
  document.getElementById('devModeMsg').textContent = r.ok
    ? '&#9989; Developer mode enabled. Check your iPhone for a confirmation prompt.'
    : `&#10060; ${r.message}`;
}

async function mountDevImage() {
  if (!selectedDevice) { alert('No device connected.'); return; }
  document.getElementById('devModeMsg').textContent = 'Mounting developer image&#8230;';
  const r = await api(`/api/developer/${selectedDevice.udid}/mount`, { method: 'POST' });
  document.getElementById('devModeMsg').textContent = r.ok
    ? `&#9989; ${r.message}`
    : `&#10060; ${r.message}`;
}

// ── Setup / deployment ────────────────────────────────────────────────────
function setupPayload() {
  return {
    backup_root: document.getElementById('setupBackupRoot').value.trim(),
    libimobiledevice_path: document.getElementById('setupLibPath').value.trim(),
    host: document.getElementById('setupHost').value.trim() || '127.0.0.1',
    port: Number(document.getElementById('setupPort').value || 5055),
    bind_all_interfaces: document.getElementById('setupBindAll').checked,
    api_token: document.getElementById('setupApiToken').value.trim(),
  };
}

function renderSetupResults(result) {
  const el = document.getElementById('setupResults');
  if (!el) return;
  if (!result || !result.checks) {
    el.textContent = JSON.stringify(result, null, 2);
    return;
  }
  el.textContent = result.checks.map(item =>
    `${item.ok ? 'OK' : 'FAIL'}  ${item.name}: ${item.message}`
  ).join('\n');
}

function showSetupOverlay(show) {
  const overlay = document.getElementById('setupOverlay');
  const shell = document.querySelector('.shell');
  const topbar = document.querySelector('.topbar');
  if (overlay) overlay.style.display = show ? 'flex' : 'none';
  if (shell) shell.style.filter = show ? 'blur(2px)' : '';
  if (topbar) topbar.style.pointerEvents = show ? 'none' : '';
}

async function loadSetupStatus() {
  const res = await fetch('/api/setup/status');
  const data = await res.json();
  const pathEl = document.getElementById('setupConfigPath');
  if (pathEl) pathEl.textContent = 'Config file: ' + (data.config?.config_path || 'backend/config.json');
  if (data.detected_libimobiledevice_path && document.getElementById('setupLibPath')) {
    document.getElementById('setupLibPath').placeholder = 'Detected: ' + data.detected_libimobiledevice_path;
  }
  if (data.config?.backup_root) {
    document.getElementById('setupBackupRoot').value = data.config.backup_root;
  }
  if (data.config?.libimobiledevice_path) {
    document.getElementById('setupLibPath').value = data.config.libimobiledevice_path;
  }
  return data;
}

async function testSetupPaths() {
  const el = document.getElementById('setupResults');
  if (el) el.textContent = 'Testing paths...';
  try {
    const res = await fetch('/api/setup/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(setupPayload()),
    });
    const data = await res.json();
    renderSetupResults(data);
  } catch (e) {
    if (el) el.textContent = 'Test failed: ' + JSON.stringify(e);
  }
}

async function completeSetup() {
  const el = document.getElementById('setupResults');
  if (el) el.textContent = 'Saving deployment settings...';
  try {
    const res = await fetch('/api/setup/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(setupPayload()),
    });
    const data = await res.json();
    renderSetupResults(data);
    if (!data.ok) return;

    if (data.generated_api_token) {
      localStorage.setItem('iphoneManagerApiKey', data.generated_api_token);
      alert('Setup complete. An API token was generated and saved in this browser.');
    }

    showSetupOverlay(false);
    detectDevice();
    if (data.restart_required) {
      alert('Network settings changed. Restart the app/service to apply host/port changes.');
    }
  } catch (e) {
    if (el) el.textContent = 'Setup failed: ' + JSON.stringify(e);
  }
}

async function ensureSetupComplete() {
  try {
    const data = await loadSetupStatus();
    if (!data.setup_complete) {
      showSetupOverlay(true);
      return false;
    }
    showSetupOverlay(false);
    return true;
  } catch (e) {
    showSetupOverlay(true);
    return false;
  }
}

// ── Config / Backup Location ──────────────────────────────────────────────
async function loadConfig() {
  try {
    const data = await api('/api/config');
    const rootEl = document.getElementById('cfgBackupRoot');
    if (rootEl) rootEl.value = data.backup_root || '';
    const hostEl = document.getElementById('cfgHost');
    if (hostEl) hostEl.value = data.host || '127.0.0.1';
    const portEl = document.getElementById('cfgPort');
    if (portEl) portEl.value = data.port || 5055;
    const bindEl = document.getElementById('cfgBindAll');
    if (bindEl) bindEl.checked = !!data.bind_all_interfaces;
    const sizesEl = document.getElementById('cfgComputeSizes');
    if (sizesEl) sizesEl.checked = !!data.compute_backup_sizes;
    const keyEl = document.getElementById('cfgApiKey');
    if (keyEl) keyEl.value = getApiKey();
    const msg = document.getElementById('cfgMsg');
    if (msg) {
      msg.textContent = `Backup: ${data.backup_root || '—'} · Config: ${data.config_path || '—'} · Token: ${data.api_token_set ? 'yes' : 'no'}`;
    }
  } catch (e) {
    const msg = document.getElementById('cfgMsg');
    if (msg) msg.textContent = 'Error loading config';
  }
}

async function saveBackupLocation() {
  const root = document.getElementById('cfgBackupRoot').value.trim();
  if (!root) { alert('Enter a backup path.'); return; }
  const msg = document.getElementById('cfgMsg');
  msg.textContent = 'Saving...';
  try {
    const data = await api('/api/config', {
      method: 'POST',
      body: JSON.stringify({ backup_root: root })
    });
    msg.textContent = 'Saved backup path: ' + data.config.backup_root;
    msg.style.color = 'var(--green)';
  } catch (e) {
    msg.textContent = 'Error: ' + JSON.stringify(e);
    msg.style.color = 'var(--red)';
  }
}

function saveApiKey() {
  const key = document.getElementById('cfgApiKey').value.trim();
  if (key) localStorage.setItem('iphoneManagerApiKey', key);
  else localStorage.removeItem('iphoneManagerApiKey');
  const msg = document.getElementById('cfgMsg');
  if (msg) {
    msg.textContent = key ? 'API key saved in this browser.' : 'API key cleared from this browser.';
    msg.style.color = 'var(--green)';
  }
}

async function saveNetworkSettings() {
  const msg = document.getElementById('cfgMsg');
  msg.textContent = 'Saving network settings...';
  try {
    const payload = {
      host: document.getElementById('cfgHost').value.trim() || '127.0.0.1',
      port: Number(document.getElementById('cfgPort').value || 5055),
      bind_all_interfaces: document.getElementById('cfgBindAll').checked,
      compute_backup_sizes: document.getElementById('cfgComputeSizes').checked,
    };
    const data = await api('/api/config', { method: 'POST', body: JSON.stringify(payload) });
    msg.textContent = `Saved server settings. Listening on ${data.config.host}:${data.config.port}`;
    msg.style.color = 'var(--green)';
  } catch (e) {
    msg.textContent = 'Error: ' + JSON.stringify(e);
    msg.style.color = 'var(--red)';
  }
}

function setBackupPreset(path) {
  document.getElementById('cfgBackupRoot').value = path;
}


// ── Resizable Sidebar ─────────────────────────────────────────────────────
(function initResizableSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;

  // Add drag handle
  const handle = document.createElement('div');
  handle.id = 'sidebarHandle';
  handle.style.cssText = `
    position:absolute; right:-4px; top:0; bottom:0; width:8px;
    cursor:col-resize; z-index:50; background:transparent;
  `;
  sidebar.style.position = 'relative';
  sidebar.appendChild(handle);

  // Restore saved width
  const saved = localStorage.getItem('sidebarWidth');
  if (saved) sidebar.style.width = saved + 'px';

  let dragging = false, startX = 0, startW = 0;

  handle.addEventListener('mousedown', e => {
    dragging = true;
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newW = Math.max(160, Math.min(400, startW + e.clientX - startX));
    sidebar.style.width = newW + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.setItem('sidebarWidth', sidebar.offsetWidth);
  });

  // Double-click handle to collapse/expand
  let collapsed = false, prevWidth = 240;
  handle.addEventListener('dblclick', () => {
    if (!collapsed) {
      prevWidth = sidebar.offsetWidth;
      sidebar.style.width = '0px';
      sidebar.style.overflow = 'hidden';
      collapsed = true;
    } else {
      sidebar.style.width = prevWidth + 'px';
      sidebar.style.overflow = '';
      collapsed = false;
    }
  });
})();

// ── WiFi Backup ───────────────────────────────────────────────────────────
let wifiBackupMode = false;

async function detectWifiDevices() {
  const el = document.getElementById('backupDeviceList');
  el.innerHTML = "<p class='muted'>&#128246; Scanning network for iPhone&#8230; (make sure iPhone is on same WiFi and paired)</p>";
  try {
    const data = await api('/api/devices/wifi');
    const devices = data.devices || [];
    if (!devices.length) {
      el.innerHTML = "<p class='muted'>No iPhone found on WiFi.<br><span class='small'>Ensure: same network, Settings &rarr; General &rarr; VPN &amp; Device Management &rarr; trust this computer, and WiFi sync enabled in Finder/iTunes.</span></p>";
      return;
    }
    window._detectedDevices = devices;
    updateBackupDeviceList(devices);
    selectedDevice = devices[0];
  } catch (e) {
    el.innerHTML = `<p class='muted'>WiFi scan error: ${esc(e.message || JSON.stringify(e))}</p>`;
  }
}

function toggleWifiMode() {
  wifiBackupMode = document.getElementById('wifiToggle').checked;
  if (wifiBackupMode) {
    detectWifiDevices();
  } else {
    detectDevice();
  }
}

// ── Mirror pane drag divider ─────────────────────────────────────────────────────
(function initMirrorPane() {
  const STORE = 'mirrorPaneLeftW';

  function setup() {
    const divider = document.getElementById('mirrorDivider');
    const paneA   = document.getElementById('mirrorPaneLeft');
    if (!divider || !paneA || divider.dataset.init) return;
    divider.dataset.init = '1';

    const saved = localStorage.getItem(STORE);
    if (saved) paneA.style.width = saved + 'px';

    let dragging = false, startX = 0, startW = 0;

    divider.addEventListener('mousedown', e => {
      dragging = true;
      startX = e.clientX;
      startW = paneA.offsetWidth;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const w = Math.max(120, Math.min(700, startW + e.clientX - startX));
      paneA.style.width = w + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      localStorage.setItem(STORE, paneA.offsetWidth);
    });
  }

  const _orig = showSection;
  window.showSection = function(name) {
    _orig(name);
    if (name === 'mirror') setTimeout(setup, 50);
  };
})();

// Toggle collapse mirror left pane
let _mirrorPaneCollapsed = false, _mirrorPanePrevW = 340;
function toggleMirrorPane() {
  const pane = document.getElementById('mirrorPaneLeft');
  const btn  = document.getElementById('btnCollapseLeft');
  if (!pane) return;
  if (!_mirrorPaneCollapsed) {
    _mirrorPanePrevW = pane.offsetWidth;
    pane.style.width = '0px';
    pane.style.overflow = 'hidden';
    if (btn) btn.textContent = '►';
    _mirrorPaneCollapsed = true;
  } else {
    pane.style.width = _mirrorPanePrevW + 'px';
    pane.style.overflow = '';
    if (btn) btn.textContent = '◄';
    _mirrorPaneCollapsed = false;
  }
}
