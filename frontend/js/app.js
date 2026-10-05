// NetPulse Pro - Main Application Logic (Production Hardened)

let spectrumChart5G = null;
let spectrumChart24G = null;
let pingChart = null;
let dnsChart = null;
let historyChart = null;
let liveSpeedChart = null;

let appState = {
  activeTab: 'tab-overview',
  gatewayIp: '192.168.1.1',
  currentChannel: 0,
  currentBand: '5 GHz',
  historyHours: 1,
  isPolling: false,
  peakDlMbps: 0.0,
  peakUlMbps: 0.0,
  lastSecurityData: null,
  versionInfo: null
};

// Safe DOM manipulation helpers with strict null-checking
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = (text !== undefined && text !== null) ? String(text) : '';
  return el;
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = (html !== undefined && html !== null) ? String(html) : '';
  return el;
}

function setClass(id, className) {
  const el = document.getElementById(id);
  if (el) el.className = className;
  return el;
}

function getValue(id, defaultVal = '') {
  const el = document.getElementById(id);
  return el ? el.value.trim() : defaultVal;
}

function getChecked(id, defaultVal = false) {
  const el = document.getElementById(id);
  return el ? el.checked : defaultVal;
}

let isFetchingBandwidth = false;

// Real-Time Speed & Bandwidth Throughput Engine
async function fetchBandwidthRealtime() {
  if (isFetchingBandwidth || document.hidden) return;
  isFetchingBandwidth = true;

  try {
    const res = await fetch('/api/bandwidth-realtime');
    if (!res.ok) return;
    const data = await res.json();

    // Batch all DOM updates in requestAnimationFrame to eliminate layout thrashing
    requestAnimationFrame(() => {
      const numDl = Number(data.download_mbps || 0);
      const numUl = Number(data.upload_mbps || 0);
      const dlMbps = numDl.toFixed(2);
      const ulMbps = numUl.toFixed(2);
      const dlKbps = Math.round(data.download_kbps || 0);
      const ulKbps = Math.round(data.upload_kbps || 0);

      // Track Peak Speeds
      if (numDl > appState.peakDlMbps) {
        appState.peakDlMbps = numDl;
        setText('ov-peak-dl-mbps', `${dlMbps} Mbps`);
      }
      if (numUl > appState.peakUlMbps) {
        appState.peakUlMbps = numUl;
        setText('ov-peak-ul-mbps', `${ulMbps} Mbps`);
      }

      // Header Realtime Pill
      setText('rt-dl-speed', dlMbps);
      setText('rt-ul-speed', ulMbps);

      // Overview Tab Bandwidth Cards
      setText('ov-rt-dl-mbps', dlMbps);
      setText('ov-rt-ul-mbps', ulMbps);
      setText('ov-rt-dl-kbps', `${dlKbps.toLocaleString()} kbps`);
      setText('ov-rt-ul-kbps', `${ulKbps.toLocaleString()} kbps`);

      const totalMB = Math.round(((data.bytes_recv_total || 0) + (data.bytes_sent_total || 0)) / (1024 * 1024));
      setText('ov-rt-total-mb', totalMB.toLocaleString());
      setText('ov-rt-interface-name', data.interface || 'Wi-Fi');

      const totalPackets = ((data.packets_recv_total || 0) + (data.packets_sent_total || 0));
      setText('ov-rt-packets', totalPackets > 0 ? totalPackets.toLocaleString() : '--');

      // Update Live Speeds Over Time Area Chart
      if (liveSpeedChart && liveSpeedChart.data) {
        const now = new Date();
        const timeLabel = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;

        liveSpeedChart.data.labels.push(timeLabel);
        liveSpeedChart.data.datasets[0].data.push(numDl);
        liveSpeedChart.data.datasets[1].data.push(numUl);

        // Keep rolling buffer of 30 points
        if (liveSpeedChart.data.labels.length > 30) {
          liveSpeedChart.data.labels.shift();
          liveSpeedChart.data.datasets[0].data.shift();
          liveSpeedChart.data.datasets[1].data.shift();
        }

        liveSpeedChart.update('none');
      }
    });
  } catch (err) {
    // Non-blocking catch
  } finally {
    isFetchingBandwidth = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initLucide();
  initTabs();
  initCharts();
  loadInitialData();

  // Background polling for health status every 12s
  setInterval(() => {
    if (appState.isPolling || document.hidden) return;
    appState.isPolling = true;
    Promise.allSettled([
      fetchSystemStatus(false),
      fetchSystemHardware(),
      (appState.activeTab === 'tab-timeline') ? fetchHistoryAndIncidents(false) : Promise.resolve()
    ]).finally(() => {
      appState.isPolling = false;
    });
  }, 12000);

  // Real-time drop sentry status polling every 6s for immediate fix banner
  setInterval(fetchDaemonStatus, 6000);

  // Real-time Bandwidth throughput polling every 2s
  setInterval(fetchBandwidthRealtime, 2000);
  fetchBandwidthRealtime();
  fetchDaemonStatus();
});

function initLucide() {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
}

// -------------------------------------------------------------
// TAB NAVIGATION
// -------------------------------------------------------------
function toggleSidebar(open) {
  const sidebar = document.getElementById('app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sidebar) return;

  if (open === undefined) {
    sidebar.classList.toggle('-translate-x-full');
    if (backdrop) backdrop.classList.toggle('hidden');
  } else if (open) {
    sidebar.classList.remove('-translate-x-full');
    if (backdrop) backdrop.classList.remove('hidden');
  } else {
    sidebar.classList.add('-translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
  }
}

const TAB_TITLES = {
  'tab-overview': { icon: 'activity', title: 'Overview & Health', color: 'text-cyan-400' },
  'tab-timeline': { icon: 'history', title: '24/7 Outage Timeline', color: 'text-cyan-400' },
  'tab-alerts': { icon: 'bell', title: 'Alerts & Phone Push', color: 'text-amber-400' },
  'tab-drops': { icon: 'stethoscope', title: 'Drop & Disconnect Doctor', color: 'text-rose-400' },
  'tab-spectrum': { icon: 'radio-tower', title: 'Wi-Fi Spectrum Radar', color: 'text-blue-400' },
  'tab-ping': { icon: 'target', title: 'Latency & Loss Scope', color: 'text-emerald-400' },
  'tab-bufferbloat': { icon: 'gauge', title: 'Bufferbloat & Speed', color: 'text-indigo-400' },
  'tab-processes': { icon: 'cpu', title: 'Bandwidth Hogs', color: 'text-teal-400' },
  'tab-security': { icon: 'shield-check', title: 'Security & Vulnerabilities', color: 'text-emerald-400' },
  'tab-dns': { icon: 'zap', title: 'DNS Turbo Benchmark', color: 'text-amber-400' },
  'tab-repair': { icon: 'wrench', title: 'Local Repair Center', color: 'text-cyan-400' },
};

function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const targetId = tab.getAttribute('data-tab');
      appState.activeTab = targetId;

      document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
      });

      const activeContent = document.getElementById(targetId);
      if (activeContent) {
        activeContent.classList.remove('hidden');
      }

      // Update top header title
      const meta = TAB_TITLES[targetId] || { icon: 'activity', title: 'Overview & Health', color: 'text-cyan-400' };
      const topTitle = document.getElementById('top-view-title');
      if (topTitle) {
        topTitle.innerHTML = `<i data-lucide="${meta.icon}" class="w-4 h-4 ${meta.color}"></i> ${escapeHtml(meta.title)}`;
      }

      // Close mobile sidebar drawer
      if (window.innerWidth < 1024) {
        toggleSidebar(false);
      }

      // Lazy load tab data on click
      if (targetId === 'tab-timeline') fetchHistoryAndIncidents(true);
      else if (targetId === 'tab-alerts') loadNotificationSettings();
      else if (targetId === 'tab-spectrum') fetchWifiScan(false);
      else if (targetId === 'tab-ping') runPingDiagnostic(false);
      else if (targetId === 'tab-drops') fetchDropsReport(false);
      else if (targetId === 'tab-dns') runDnsBenchmark(false);
      else if (targetId === 'tab-processes') fetchProcesses(false);
      else if (targetId === 'tab-security') fetchSecurityAudit(false);

      initLucide();
    });
  });
}

// -------------------------------------------------------------
// INITIAL DATA LOAD
// -------------------------------------------------------------
async function loadInitialData() {
  await fetchSystemStatus(true);
  fetchHealthScore();
  fetchSystemHardware();
  runPingDiagnostic(false);
  fetchSecurityAudit(false);
  fetchVersionInfo(false);
}

async function refreshAll() {
  showToast('Refreshing', 'Gathering fresh network telemetry...', 'info');
  await fetchSystemStatus(true);
  await fetchHealthScore();
  if (appState.activeTab === 'tab-spectrum') await fetchWifiScan(true);
  else if (appState.activeTab === 'tab-ping') await runPingDiagnostic(true);
  else if (appState.activeTab === 'tab-drops') await fetchDropsReport(true);
  else if (appState.activeTab === 'tab-dns') await runDnsBenchmark(true);
  else if (appState.activeTab === 'tab-processes') await fetchProcesses(true);
  else if (appState.activeTab === 'tab-timeline') await fetchHistoryAndIncidents(true);
  else if (appState.activeTab === 'tab-security') await fetchSecurityAudit(true);
  showToast('Updated', 'Diagnostics up to date.', 'success');
}

// -------------------------------------------------------------
// API: SYSTEM STATUS & TELEMETRY
// -------------------------------------------------------------
async function fetchSystemStatus(fullUpdate = true) {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Admin privileges badge
    const adminBadge = document.getElementById('admin-badge');
    if (adminBadge) {
      if (data.admin_privileges) {
        adminBadge.textContent = 'Admin Mode: Active';
        adminBadge.className = 'text-xs px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
      } else {
        adminBadge.textContent = 'Standard Mode (UAC for hardware settings)';
        adminBadge.className = 'text-xs px-2 py-0.5 rounded font-medium bg-slate-800 text-slate-400 border border-slate-700';
      }
    }

    const wifi = data.wifi || {};
    appState.gatewayIp = data.default_gateway || '192.168.1.1';
    appState.currentChannel = wifi.channel || 0;
    appState.currentBand = wifi.band || '5 GHz';

    // Header Telemetry
    const ssidElem = document.getElementById('header-ssid');
    if (ssidElem) {
      if (wifi.connected) {
        ssidElem.textContent = wifi.is_ethernet ? 'Wired Ethernet' : (wifi.ssid || 'Connected');
      } else {
        ssidElem.textContent = 'Disconnected';
      }
    }

    const bandElem = document.getElementById('header-band');
    if (bandElem) {
      bandElem.innerHTML = `<i data-lucide="radio" class="w-3.5 h-3.5 text-cyan-400"></i> ${escapeHtml(wifi.band || '-- GHz')}`;
    }

    const speedElem = document.getElementById('header-speed');
    if (speedElem) {
      speedElem.innerHTML = `<i data-lucide="gauge" class="w-3.5 h-3.5 text-emerald-400"></i> ${escapeHtml(String(wifi.rx_rate_mbps || '--'))} Mbps`;
    }

    const rssiElem = document.getElementById('header-rssi');
    if (rssiElem) {
      const rssiVal = wifi.is_ethernet ? '0' : (wifi.rssi_dbm !== undefined ? String(wifi.rssi_dbm) : '--');
      rssiElem.innerHTML = `<i data-lucide="signal" class="w-3.5 h-3.5 text-amber-400"></i> ${rssiVal} dBm`;
    }

    // Overview Tab
    setText('adapter-chip-name', wifi.adapter || 'Network Adapter');
    setText('ov-signal-percent', `${wifi.signal_percent !== undefined ? wifi.signal_percent : 0}%`);
    setText('ov-rssi-dbm', `${wifi.rssi_dbm !== undefined ? wifi.rssi_dbm : -90} dBm`);

    const sigRating = document.getElementById('ov-signal-rating');
    if (sigRating) {
      sigRating.textContent = wifi.signal_rating || (wifi.connected ? 'Good' : 'Disconnected');
      sigRating.style.color = wifi.signal_color || (wifi.connected ? '#10B981' : '#EF4444');
    }

    setText('ov-link-speed', wifi.rx_rate_mbps || '--');
    setText('ov-radio-type', wifi.radio_type || '802.11');

    const channelDisplay = wifi.channel ? ` (Ch ${wifi.channel})` : '';
    setText('ov-band-channel', `${wifi.band || ''}${channelDisplay}`);
    setText('ov-gateway-ip', appState.gatewayIp);

    const routerBtn = document.getElementById('btn-open-router-settings');
    if (routerBtn) routerBtn.href = `http://${appState.gatewayIp}`;

    const guideRouterBtn = document.getElementById('btn-guide-router-link');
    if (guideRouterBtn) guideRouterBtn.href = `http://${appState.gatewayIp}`;

    initLucide();
  } catch (err) {
    console.error('Failed to fetch status:', err);
    const ssidElem = document.getElementById('header-ssid');
    if (ssidElem) ssidElem.textContent = 'Server Offline / Busy';
    const adminBadge = document.getElementById('admin-badge');
    if (adminBadge) {
      adminBadge.textContent = 'Reconnecting...';
      adminBadge.className = 'text-xs px-2 py-0.5 rounded font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30';
    }
  }
}

// -------------------------------------------------------------
// API: HEALTH SCORE & ASSESSMENT
// -------------------------------------------------------------
async function fetchHealthScore() {
  try {
    const res = await fetch('/api/full-health');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const score = data.score !== undefined ? data.score : 85;
    const grade = data.grade || 'A';
    const gradeText = data.grade_text || 'Excellent';
    const color = data.badge_color || '#10B981';

    const gradeBadge = document.getElementById('health-badge');
    if (gradeBadge) {
      gradeBadge.textContent = grade;
      gradeBadge.style.borderColor = color;
      gradeBadge.style.color = color;
    }

    setText('health-grade-text', gradeText);
    setText('health-score-percent', `${score}/100`);

    const progressBar = document.getElementById('health-progress-bar');
    if (progressBar) {
      progressBar.style.width = `${score}%`;
      progressBar.style.backgroundColor = color;
    }

    const summaryDesc = document.getElementById('health-summary-desc');
    if (summaryDesc) {
      const wifi = data.wifi || {};
      const ping = data.gateway_ping || {};
      if (wifi.connected) {
        summaryDesc.textContent = `Physical link: ${wifi.rx_rate_mbps || 0} Mbps on ${wifi.band || 'Network'}. Local router response time: ${ping.avg_ms || 1}ms (${ping.loss_percent || 0}% packet loss).`;
      } else {
        summaryDesc.textContent = 'Network is disconnected. No physical link established with local router.';
      }
    }

    updatePillarsAndReadiness(data, null);
  } catch (err) {
    console.error('Failed to fetch health score:', err);
    setText('health-grade-text', 'Status Pending');
    setText('health-score-percent', '--/100');
  }
}

// -------------------------------------------------------------
// API: PING & MULTI-HOP ISOLATION
// -------------------------------------------------------------
async function runPingDiagnostic(notify = false) {
  if (notify) showToast('Diagnosing', 'Pinging local router and public endpoints...', 'info');

  try {
    const res = await fetch('/api/ping-test');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    updatePillarsAndReadiness(null, data);

    setText('ping-verdict-title', data.verdict || 'Diagnosis Complete');
    setText('ping-verdict-detail', `${data.root_cause || ''} ${data.recommendation || ''}`);

    // Update Overview Verdict Box
    setText('ov-verdict-title', data.verdict || 'Diagnosis Complete');
    setText('ov-verdict-desc', data.root_cause || 'Network link audited.');

    const verdictBanner = document.getElementById('ping-verdict-banner');
    const ovBox = document.getElementById('ov-verdict-box');
    const ovIcon = document.getElementById('ov-verdict-icon');

    if (data.verdict_type === 'danger') {
      if (verdictBanner) verdictBanner.className = 'glass-panel p-6 border-rose-500/50 bg-rose-950/20';
      if (ovBox) ovBox.className = 'p-4 rounded-xl border border-rose-500/40 bg-rose-950/20 flex items-start gap-3';
      if (ovIcon) ovIcon.className = 'p-2 rounded-lg bg-rose-500/20 text-rose-400 mt-0.5';
    } else if (data.verdict_type === 'warning') {
      if (verdictBanner) verdictBanner.className = 'glass-panel p-6 border-amber-500/50 bg-amber-950/20';
      if (ovBox) ovBox.className = 'p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 flex items-start gap-3';
      if (ovIcon) ovIcon.className = 'p-2 rounded-lg bg-amber-500/20 text-amber-400 mt-0.5';
    } else {
      if (verdictBanner) verdictBanner.className = 'glass-panel p-6 border-cyan-500/30';
      if (ovBox) ovBox.className = 'p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex items-start gap-3';
      if (ovIcon) ovIcon.className = 'p-2 rounded-lg bg-emerald-500/10 text-emerald-400 mt-0.5';
    }

    const hops = data.hops || {};
    const gw = hops['Local Gateway (Router)'] || {};
    const cf = hops['Cloudflare DNS (Edge)'] || {};
    const gg = hops['Google Anycast'] || {};

    // Hop 1 (Gateway)
    setText('gw-avg-ms', gw.avg_ms !== undefined ? gw.avg_ms : '--');
    setText('gw-loss-val', `${gw.loss_percent !== undefined ? gw.loss_percent : 0}%`);
    setText('gw-jitter-val', `${gw.jitter_ms !== undefined ? gw.jitter_ms : 0} ms`);

    // Hop 2 (Cloudflare)
    setText('cf-avg-ms', cf.avg_ms !== undefined ? cf.avg_ms : '--');
    setText('cf-loss-val', `${cf.loss_percent !== undefined ? cf.loss_percent : 0}%`);
    setText('cf-jitter-val', `${cf.jitter_ms !== undefined ? cf.jitter_ms : 0} ms`);

    // Hop 3 (Google)
    setText('gg-avg-ms', gg.avg_ms !== undefined ? gg.avg_ms : '--');
    setText('gg-loss-val', `${gg.loss_percent !== undefined ? gg.loss_percent : 0}%`);
    setText('gg-jitter-val', `${gg.jitter_ms !== undefined ? gg.jitter_ms : 0} ms`);

    // Update Ping Chart safely
    updatePingChart(gw.raw_times || [], cf.raw_times || [], gg.raw_times || []);

    if (notify) showToast('Complete', 'Latency and packet loss diagnostics refreshed.', 'success');
  } catch (err) {
    console.error('Ping test error:', err);
    setText('ping-verdict-title', 'Diagnostic Offline');
    setText('ping-verdict-detail', 'Could not run ping probe. Verify that the NetPulse backend server is active.');
    if (notify) showToast('Error', 'Failed to run ping diagnostic: ' + err.message, 'error');
  }
}

// -------------------------------------------------------------
// API: MTU DISCOVERY
// -------------------------------------------------------------
async function runMtuTest(btn) {
  if (btn) btn.disabled = true;
  showToast('Testing MTU', 'Probing packet fragmentation thresholds...', 'info');

  try {
    const res = await fetch('/api/mtu-test');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const badge = document.getElementById('mtu-badge');
    if (badge) {
      badge.textContent = `MTU ${data.optimal_mtu}`;
      badge.className = data.standard_ethernet
        ? 'px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400'
        : 'px-2 py-0.5 rounded text-xs font-bold bg-amber-500/20 text-amber-400';
    }

    setText('mtu-desc', data.description || 'MTU test finished.');
    showToast('MTU Verified', data.description || 'Completed', data.standard_ethernet ? 'success' : 'warning');
  } catch (err) {
    showToast('MTU Test Failed', err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// -------------------------------------------------------------
// API: WI-FI SPECTRUM & BUSY CHANNELS
// -------------------------------------------------------------
async function fetchWifiScan(notify = false) {
  if (notify) showToast('Scanning Spectrum', 'Auditing all visible 2.4GHz & 5GHz channels...', 'info');

  try {
    const res = await fetch('/api/wifi-scan');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const analysis = data.analysis || {};
    const networks = data.networks || [];

    // Current badge & advisor
    setText('spectrum-current-badge', `Channel ${analysis.current_channel || 0} (${analysis.current_band || '5 GHz'})`);
    setText('spectrum-advisor-text', analysis.recommendation || 'Channels scanned.');
    setText('best-5g-channel', `Ch ${analysis.best_channel_5g || 36}`);
    setText('best-24-channel', `Ch ${analysis.best_channel_24 || 1}`);

    // Update charts
    updateSpectrumCharts(analysis.channels_5g || [], analysis.channels_24 || [], analysis.current_channel || 0);

    // Update table
    renderNearbyNetworksTable(networks);

    if (notify) showToast('Scan Complete', `Analyzed ${analysis.total_visible_bssids || 0} access points.`, 'success');
  } catch (err) {
    console.error('Scan error:', err);
    setText('spectrum-advisor-text', 'Wireless scan unavailable. The Wi-Fi adapter may be disabled or operating in pure wired Ethernet mode.');
    const tbody = document.getElementById('nearby-networks-tbody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-amber-400">Wi-Fi scan failed: ${escapeHtml(err.message)}</td></tr>`;
    }
    if (notify) showToast('Scan Failed', err.message, 'error');
  }
}

function renderNearbyNetworksTable(networks) {
  const tbody = document.getElementById('nearby-networks-tbody');
  const countElem = document.getElementById('total-bssids-count');
  if (!tbody) return;

  let allBssids = [];
  (networks || []).forEach(net => {
    (net.bssids || []).forEach(b => {
      allBssids.push({
        ssid: net.ssid || 'Hidden',
        ...b
      });
    });
  });

  if (countElem) countElem.textContent = `${allBssids.length} Access Point(s) Visible`;

  if (allBssids.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No surrounding networks found or operating in wired mode.</td></tr>`;
    return;
  }

  tbody.innerHTML = allBssids.map(b => {
    const isCurrent = b.channel === appState.currentChannel;
    return `
      <tr class="${isCurrent ? 'bg-cyan-950/20 font-semibold' : 'hover:bg-slate-800/40'}">
        <td class="p-3 font-medium text-white flex items-center gap-1.5">
          ${isCurrent ? '<span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>' : ''}
          ${escapeHtml(b.ssid)}
        </td>
        <td class="p-3 text-slate-300">${escapeHtml(b.band || '2.4 GHz')}</td>
        <td class="p-3 font-mono text-cyan-400">${b.channel || '--'}</td>
        <td class="p-3">
          <div class="flex items-center gap-2">
            <span class="text-white">${b.signal_percent || 0}%</span>
            <div class="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div class="bg-emerald-500 h-1.5 rounded-full" style="width: ${b.signal_percent || 0}%"></div>
            </div>
          </div>
        </td>
        <td class="p-3 font-mono text-slate-400">${b.rssi_dbm || -90} dBm</td>
        <td class="p-3 text-slate-400">${escapeHtml(b.radio_type || '802.11')}</td>
        <td class="p-3 text-slate-300">${b.utilization_percent > 0 ? `${b.utilization_percent}%` : 'N/A'}</td>
        <td class="p-3 font-mono text-slate-500 text-xs">${escapeHtml(b.bssid || '')}</td>
      </tr>
    `;
  }).join('');
}

// -------------------------------------------------------------
// API: DISCONNECT & DROP DOCTOR
// -------------------------------------------------------------
async function fetchDropsReport(notify = false) {
  if (notify) showToast('Analyzing Logs', 'Reading Windows WLAN AutoConfig operational log...', 'info');

  try {
    const res = await fetch('/api/drops?days=7');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    setText('stat-total-drops', data.total_disconnects || 0);
    setText('stat-driver-drops', data.driver_disconnects || 0);
    setText('stat-signal-drops', data.signal_disconnects || 0);
    setText('stat-user-drops', data.user_disconnects || 0);

    // Doctor findings & recommendations
    const recList = document.getElementById('doctor-recommendations-list');
    if (recList) {
      let html = '';
      (data.findings || []).forEach(f => {
        html += `<div class="p-3 rounded-lg bg-slate-800/50 border border-slate-700/60 text-xs text-slate-200">${escapeHtml(f)}</div>`;
      });

      (data.recommended_fixes || []).forEach(rf => {
        html += `
          <div class="p-3 rounded-lg bg-cyan-950/30 border border-cyan-500/40 flex items-center justify-between gap-4">
            <div>
              <h5 class="text-xs font-bold text-cyan-300">${escapeHtml(rf.title)}</h5>
              <p class="text-xs text-slate-400">${escapeHtml(rf.reason)}</p>
            </div>
            <button onclick="runSingleAction('${escapeHtml(rf.action)}', this)" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs rounded-lg transition whitespace-nowrap">
              ${escapeHtml(rf.button_text)}
            </button>
          </div>
        `;
      });

      recList.innerHTML = html || '<p class="text-xs text-slate-400">No anomalies detected.</p>';
    }

    // Timeline table
    const tbody = document.getElementById('drops-timeline-tbody');
    if (tbody) {
      const timeline = data.timeline || [];
      if (timeline.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-slate-400">No recent disconnection events recorded.</td></tr>`;
      } else {
        tbody.innerHTML = timeline.map(ev => {
          let badgeClass = 'bg-slate-800 text-slate-300';
          if (ev.type === 'disconnect') badgeClass = 'bg-rose-500/20 text-rose-400 border border-rose-500/30';
          else if (ev.type === 'connect') badgeClass = 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
          else if (ev.type === 'error') badgeClass = 'bg-amber-500/20 text-amber-400 border border-amber-500/30';

          return `
            <tr class="hover:bg-slate-800/40">
              <td class="p-3 font-mono text-slate-300">${escapeHtml(ev.timestamp)}</td>
              <td class="p-3"><span class="px-2 py-0.5 rounded text-xs font-medium ${badgeClass}">${escapeHtml(ev.category)}</span></td>
              <td class="p-3 text-white">${escapeHtml(ev.summary)}</td>
              <td class="p-3 text-slate-400 font-mono text-xs">${escapeHtml(ev.reason || 'None')}</td>
              <td class="p-3 text-slate-400">${escapeHtml(ev.ssid || '--')}</td>
            </tr>
          `;
        }).join('');
      }
    }

    if (notify) showToast('Diagnosis Complete', 'Parsed disconnection event history.', 'success');
  } catch (err) {
    console.error('Drops report error:', err);
    const tbody = document.getElementById('drops-timeline-tbody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-amber-400">Unable to retrieve disconnection logs: ${escapeHtml(err.message)}</td></tr>`;
    }
    if (notify) showToast('Error', err.message, 'error');
  }
}

// -------------------------------------------------------------
// API: DNS TURBO BENCHMARK
// -------------------------------------------------------------
async function runDnsBenchmark(notify = false) {
  if (notify) showToast('Benchmarking DNS', 'Measuring UDP query round-trips in parallel...', 'info');

  try {
    const res = await fetch('/api/dns-benchmark');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const ranked = data.ranked_providers || [];

    // Render chart safely
    updateDnsChart(ranked);

    // Render provider cards
    const grid = document.getElementById('dns-providers-grid');
    if (grid) {
      if (ranked.length === 0) {
        grid.innerHTML = '<p class="text-xs text-slate-400 col-span-full">No DNS benchmark results available.</p>';
      } else {
        grid.innerHTML = ranked.map((p, idx) => {
          const isFastest = idx === 0 && p.responsive;
          return `
            <div class="glass-panel p-5 flex flex-col justify-between border ${isFastest ? 'border-emerald-500/40 bg-emerald-950/10' : 'border-slate-800'}">
              <div>
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <h4 class="text-sm font-bold text-white">${escapeHtml(p.name)}</h4>
                    ${isFastest ? '<span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30">Fastest</span>' : ''}
                  </div>
                  <span class="text-lg font-extrabold ${p.responsive ? 'text-cyan-400' : 'text-slate-500'} font-mono">
                    ${p.responsive ? `${p.avg_ms} ms` : 'Unreachable'}
                  </span>
                </div>
                <p class="text-xs text-slate-400 mt-1">${escapeHtml(p.description)}</p>
                <div class="mt-2 text-xs font-mono text-slate-500">
                  Primary: ${escapeHtml(p.primary)} ${p.secondary ? `| Secondary: ${escapeHtml(p.secondary)}` : ''}
                </div>
              </div>
              ${p.primary && p.id !== 'current' ? `
                <button onclick="setCustomDns('${escapeHtml(p.primary)}', '${escapeHtml(p.secondary || '')}')" class="mt-4 w-full py-2 bg-slate-800 hover:bg-cyan-600 hover:text-white rounded-lg text-xs font-semibold text-slate-200 transition">
                  Switch to ${escapeHtml(p.name)}
                </button>
              ` : ''}
            </div>
          `;
        }).join('');
      }
    }

    if (notify) showToast('Benchmark Complete', data.recommendation || 'Ranked all DNS providers.', 'success');
  } catch (err) {
    console.error('DNS Benchmark error:', err);
    const grid = document.getElementById('dns-providers-grid');
    if (grid) {
      grid.innerHTML = `<div class="col-span-full p-6 text-center text-amber-400">DNS benchmark failed: ${escapeHtml(err.message)}</div>`;
    }
    if (notify) showToast('DNS Benchmark Failed', err.message, 'error');
  }
}

async function setCustomDns(primary, secondary) {
  showToast('Configuring DNS', `Setting adapter DNS to ${primary || 'DHCP Automatic'}...`, 'info');
  try {
    const res = await fetch('/api/set-dns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary, secondary, interface_name: 'Wi-Fi' })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.success) {
      showToast('DNS Updated', data.message, 'success');
      runDnsBenchmark(false);
      fetchSystemStatus(false);
    } else {
      showToast('DNS Update Error', data.message, 'error');
    }
  } catch (err) {
    showToast('Failed to Set DNS', err.message, 'error');
  }
}

// -------------------------------------------------------------
// API: BUFFERBLOAT & SPEED TEST
// -------------------------------------------------------------
async function runBufferbloatTest(btn) {
  if (btn) btn.disabled = true;
  showToast('Measuring Bufferbloat', 'Testing unloaded vs loaded latency under throughput burst...', 'info');

  try {
    const res = await fetch('/api/bufferbloat');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const gradeBox = document.getElementById('bb-grade');
    if (gradeBox) {
      gradeBox.textContent = data.grade || '--';
      gradeBox.style.borderColor = data.badge_color || '#94A3B8';
      gradeBox.style.color = data.badge_color || '#94A3B8';
    }

    setText('bb-grade-desc', data.grade_desc || 'Grade complete.');
    setText('bb-unloaded-ms', `${data.unloaded_latency_ms !== undefined ? data.unloaded_latency_ms : '--'} ms`);
    setText('bb-loaded-ms', `${data.loaded_latency_ms !== undefined ? data.loaded_latency_ms : '--'} ms`);
    setText('bb-delta-ms', `+${data.bufferbloat_delta_ms !== undefined ? data.bufferbloat_delta_ms : '--'} ms`);
    setText('bb-speed-mbps', `${data.download_speed_mbps !== undefined ? data.download_speed_mbps : 0} Mbps`);
    setText('bb-recommendation', data.recommendation || '');

    // Prevent 'data.grade in [...]' JavaScript index check bug
    const isGoodGrade = ['A+', 'A'].includes(data.grade);
    showToast(`Bufferbloat Grade: ${data.grade}`, data.grade_desc, isGoodGrade ? 'success' : 'warning');
  } catch (err) {
    showToast('Bufferbloat Test Failed', err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// -------------------------------------------------------------
// API: ACTIVE PROCESSES & SOCKETS
// -------------------------------------------------------------
async function fetchProcesses(notify = false) {
  if (notify) showToast('Scanning Processes', 'Auditing all open network sockets and processes...', 'info');

  try {
    const res = await fetch('/api/processes');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const warnContainer = document.getElementById('process-warnings-container');
    if (warnContainer) {
      warnContainer.innerHTML = (data.warnings || []).map(w => `
        <div class="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 flex items-center gap-2">
          <i data-lucide="alert-triangle" class="w-4 h-4"></i> ${escapeHtml(w)}
        </div>
      `).join('');
      initLucide();
    }

    const tbody = document.getElementById('processes-tbody');
    if (tbody) {
      const procs = data.processes || [];
      if (procs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-slate-400">No active network processes found.</td></tr>`;
      } else {
        tbody.innerHTML = procs.map(p => `
          <tr class="hover:bg-slate-800/40">
            <td class="p-3 font-semibold text-white">${escapeHtml(p.name)}</td>
            <td class="p-3 font-mono text-slate-400">${p.pid}</td>
            <td class="p-3"><span class="px-2 py-0.5 rounded text-xs font-medium bg-slate-800 text-cyan-400">${escapeHtml(p.category)}</span></td>
            <td class="p-3 font-bold text-white">${p.connection_count} sockets</td>
            <td class="p-3 font-mono text-slate-400">${p.memory_mb} MB</td>
            <td class="p-3">
              <button onclick="killProcess(${p.pid}, '${escapeHtml(p.name)}')" class="px-2.5 py-1 bg-rose-500/10 hover:bg-rose-500 hover:text-white text-rose-400 rounded text-xs transition">
                Kill
              </button>
            </td>
          </tr>
        `).join('');
      }
    }

    if (notify) showToast('Processes Refreshed', `Inspected ${data.active_processes || 0} network-active processes.`, 'success');
  } catch (err) {
    console.error('Processes error:', err);
    const tbody = document.getElementById('processes-tbody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-amber-400">Unable to inspect processes: ${escapeHtml(err.message)}</td></tr>`;
    }
    if (notify) showToast('Failed to Fetch Processes', err.message, 'error');
  }
}

async function killProcess(pid, name) {
  if (!confirm(`Are you sure you want to terminate process '${name}' (PID ${pid})?`)) return;

  try {
    const res = await fetch('/api/terminate-process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.success) {
      showToast('Terminated', data.message, 'success');
      fetchProcesses(false);
    } else {
      showToast('Failed to Terminate', data.message, 'error');
    }
  } catch (err) {
    showToast('Kill Failed', err.message, 'error');
  }
}

// -------------------------------------------------------------
// OPTIMIZATION ACTIONS
// -------------------------------------------------------------
async function runSingleAction(action, btn) {
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="inline-block w-3 h-3 spinner mr-2"></span> Applying...`;
  }

  showToast('Executing Fix', `Applying optimization '${action}'...`, 'info');

  try {
    const res = await fetch(`/api/optimize/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.success) {
      showToast('Optimization Applied', data.message, 'success');
      fetchSystemStatus(false);
      fetchHealthScore();
    } else {
      showToast('Execution Issue', data.message, 'warning');
    }
  } catch (err) {
    showToast('Action Failed', err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Completed';
      setTimeout(() => {
        btn.textContent = 'Run Again';
      }, 2000);
    }
  }
}

// MASTER FULL AUTO-REPAIR WORKFLOW
async function triggerFullRepair() {
  const modal = document.getElementById('repair-modal');
  const container = document.getElementById('repair-steps-container');
  const statusBadge = document.getElementById('repair-modal-status');
  const closeBtn = document.getElementById('btn-close-repair-modal');

  if (modal) modal.classList.remove('hidden');
  if (closeBtn) {
    closeBtn.disabled = true;
    closeBtn.classList.add('cursor-not-allowed', 'opacity-50');
  }
  if (statusBadge) statusBadge.textContent = 'Executing Sequential Repairs...';

  const initialSteps = [
    'Flush DNS Cache & Dynamic Register',
    'Clear ARP / Neighbor Discovery Table',
    'Optimize Windows TCP Global Parameters',
    'Disable Hardware Power Saving Throttling',
    'Tune Adapter for Gaming & Low Latency',
    'Renew DHCP IP Address Lease'
  ];

  if (container) {
    container.innerHTML = initialSteps.map((s, idx) => `
      <div id="step-row-${idx}" class="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
        <span class="text-slate-300">${s}</span>
        <span class="step-status text-slate-500 font-mono">Pending</span>
      </div>
    `).join('');
  }

  try {
    const res = await fetch('/api/optimize/full_repair', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const report = data.report || [];

    report.forEach((item, idx) => {
      const row = document.getElementById(`step-row-${idx}`);
      if (row) {
        const stat = row.querySelector('.step-status');
        if (item.success) {
          row.classList.add('border-emerald-500/40', 'bg-emerald-950/20');
          if (stat) {
            stat.textContent = 'OK';
            stat.className = 'step-status text-emerald-400 font-bold';
          }
        } else {
          row.classList.add('border-amber-500/40');
          if (stat) {
            stat.textContent = 'Note';
            stat.className = 'step-status text-amber-400 font-bold';
          }
        }
      }
    });

    if (statusBadge) {
      statusBadge.textContent = `Completed (${data.successful_steps || 0}/${data.total_steps || initialSteps.length} Applied)`;
      statusBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold';
    }

    showToast('Auto-Repair Finished', data.summary || 'Repair complete.', 'success');
    fetchHealthScore();
    fetchSystemStatus(false);
  } catch (err) {
    if (statusBadge) statusBadge.textContent = 'Error during repair';
    showToast('Repair Error', err.message, 'error');
  } finally {
    if (closeBtn) {
      closeBtn.disabled = false;
      closeBtn.classList.remove('cursor-not-allowed', 'opacity-50');
      closeBtn.classList.add('bg-cyan-600', 'text-white', 'hover:bg-cyan-500');
      closeBtn.textContent = 'Close & Review Diagnostics';
    }
  }
}

function closeRepairModal() {
  const modal = document.getElementById('repair-modal');
  if (modal) modal.classList.add('hidden');
}

// -------------------------------------------------------------
// CHARTS INITIALIZATION & UPDATES (MEMORY SAFE)
// -------------------------------------------------------------
function initCharts() {
  // Destroy existing chart instances to prevent canvas memory leaks
  if (spectrumChart5G) { spectrumChart5G.destroy(); spectrumChart5G = null; }
  if (spectrumChart24G) { spectrumChart24G.destroy(); spectrumChart24G = null; }
  if (pingChart) { pingChart.destroy(); pingChart = null; }
  if (dnsChart) { dnsChart.destroy(); dnsChart = null; }
  if (historyChart) { historyChart.destroy(); historyChart = null; }
  if (liveSpeedChart) { liveSpeedChart.destroy(); liveSpeedChart = null; }

  // Chart defaults for dark theme & maximum rendering performance
  if (window.Chart) {
    Chart.defaults.color = '#94A3B8';
    Chart.defaults.borderColor = '#1E293B';
    Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
    Chart.defaults.animation = false;
    Chart.defaults.normalized = true;
  } else {
    console.warn('Chart.js library is not available.');
    return;
  }

  // 1. Spectrum 5 GHz Chart
  const ctx5g = document.getElementById('chart-spectrum-5g');
  if (ctx5g) {
    spectrumChart5G = new Chart(ctx5g, {
      type: 'bar',
      data: { labels: [], datasets: [{ label: 'Channel Health (100 = Clean)', data: [], backgroundColor: [] }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, grid: { color: '#1E293B' } },
          x: { grid: { display: false } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  // 2. Spectrum 2.4 GHz Chart
  const ctx24 = document.getElementById('chart-spectrum-24');
  if (ctx24) {
    spectrumChart24G = new Chart(ctx24, {
      type: 'bar',
      data: { labels: [], datasets: [{ label: 'Channel Score', data: [], backgroundColor: [] }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, grid: { color: '#1E293B' } },
          x: { grid: { display: false } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  // 3. Ping Hops Chart
  const ctxPing = document.getElementById('chart-ping-hops');
  if (ctxPing) {
    pingChart = new Chart(ctxPing, {
      type: 'line',
      data: {
        labels: ['Sample 1', 'Sample 2', 'Sample 3', 'Sample 4', 'Sample 5', 'Sample 6'],
        datasets: [
          { label: 'Router Gateway (Wi-Fi Link)', data: [], borderColor: '#10B981', backgroundColor: 'rgba(16, 185, 129, 0.1)', tension: 0.3, fill: true },
          { label: 'Cloudflare Edge (1.1.1.1)', data: [], borderColor: '#06B6D4', backgroundColor: 'rgba(6, 182, 212, 0.1)', tension: 0.3, fill: false },
          { label: 'Google Anycast (8.8.8.8)', data: [], borderColor: '#3B82F6', tension: 0.3, fill: false }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, grid: { color: '#1E293B' }, title: { display: true, text: 'Latency (ms)' } },
          x: { grid: { color: '#1E293B' } }
        }
      }
    });
  }

  // 4. DNS Benchmark Chart
  const ctxDns = document.getElementById('chart-dns-bench');
  if (ctxDns) {
    dnsChart = new Chart(ctxDns, {
      type: 'bar',
      data: { labels: [], datasets: [{ label: 'Average Response Time (ms)', data: [], backgroundColor: '#06B6D4', borderRadius: 6 }] },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { beginAtZero: true, grid: { color: '#1E293B' }, title: { display: true, text: 'Milliseconds (lower is better)' } },
          y: { grid: { display: false } }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  // 5. 24/7 History Timeline Chart
  const ctxHist = document.getElementById('chart-history-timeline');
  if (ctxHist) {
    historyChart = new Chart(ctxHist, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Internet Latency (ms)',
            data: [],
            borderColor: '#06B6D4',
            backgroundColor: 'rgba(6, 182, 212, 0.08)',
            borderWidth: 1.5,
            pointRadius: 1,
            tension: 0.2,
            fill: true,
            yAxisID: 'y'
          },
          {
            label: 'Gateway Latency (ms)',
            data: [],
            borderColor: '#10B981',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            fill: false,
            yAxisID: 'y'
          },
          {
            label: 'Packet Loss (%)',
            data: [],
            borderColor: '#EF4444',
            backgroundColor: 'rgba(239, 68, 68, 0.5)',
            borderWidth: 2,
            pointRadius: 2,
            fill: false,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { grid: { color: '#1E293B' }, ticks: { maxTicksLimit: 10 } },
          y: { beginAtZero: true, grid: { color: '#1E293B' }, title: { display: true, text: 'Latency (ms)' } },
          y1: { beginAtZero: true, max: 100, position: 'right', grid: { display: false }, title: { display: true, text: 'Loss (%)' } }
        }
      }
    });
  }

  // 6. Live Speeds Over Time Area Chart
  const ctxSpeed = document.getElementById('chart-speed-live');
  if (ctxSpeed) {
    liveSpeedChart = new Chart(ctxSpeed, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Download (Mbps)',
            data: [],
            borderColor: '#06B6D4',
            backgroundColor: 'rgba(6, 182, 212, 0.12)',
            borderWidth: 2,
            pointRadius: 1,
            tension: 0.3,
            fill: true
          },
          {
            label: 'Upload (Mbps)',
            data: [],
            borderColor: '#10B981',
            backgroundColor: 'rgba(16, 185, 129, 0.06)',
            borderWidth: 2,
            pointRadius: 1,
            tension: 0.3,
            fill: true
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { grid: { color: '#1E293B' }, ticks: { maxTicksLimit: 8 } },
          y: { beginAtZero: true, grid: { color: '#1E293B' }, title: { display: true, text: 'Throughput (Mbps)' } }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }
}

// -------------------------------------------------------------
// HELPER: 5 PILLARS & REAL-WORLD EXPERIENCE READINESS
// -------------------------------------------------------------
function updatePillarsAndReadiness(healthData, pingData) {
  const wifi = (healthData && healthData.wifi) || {};
  const gwPing = (healthData && healthData.gateway_ping) || (pingData && pingData.hops && pingData.hops['Local Gateway (Router)']) || {};
  const cfPing = (pingData && pingData.hops && pingData.hops['Cloudflare DNS (Edge)']) || {};

  // 1. Physical Signal / Link
  const sig = wifi.is_ethernet ? 100 : (wifi.signal_percent || 90);
  setText('pillar-sig-val', `${sig} / 100`);
  const sigBar = document.getElementById('pillar-sig-bar');
  if (sigBar) sigBar.style.width = `${sig}%`;

  // 2. Gateway Latency (<2ms = 100, 10ms = 70, >25ms = 40)
  const gwAvg = gwPing.avg_ms !== undefined ? gwPing.avg_ms : 1.2;
  const gwLoss = gwPing.loss_percent || 0;
  let gwScore = Math.max(10, Math.min(100, Math.round(100 - (gwAvg * 2.5) - (gwLoss * 2))));
  setText('pillar-gw-val', `${gwScore} / 100`);
  const gwBar = document.getElementById('pillar-gw-bar');
  if (gwBar) gwBar.style.width = `${gwScore}%`;

  // 3. Internet Latency (<30ms = 95+, 80ms = 70)
  const cfAvg = cfPing.avg_ms !== undefined ? cfPing.avg_ms : 25;
  const cfLoss = cfPing.loss_percent || 0;
  let netScore = Math.max(15, Math.min(100, Math.round(100 - (cfAvg * 0.4) - (cfLoss * 3))));
  setText('pillar-net-val', `${netScore} / 100`);
  const netBar = document.getElementById('pillar-net-bar');
  if (netBar) netBar.style.width = `${netScore}%`;

  // 4. Jitter Health
  const jit = gwPing.jitter_ms !== undefined ? gwPing.jitter_ms : 0.5;
  let jitScore = Math.max(20, Math.min(100, Math.round(100 - (jit * 6))));
  setText('pillar-jit-val', `${jitScore} / 100`);
  const jitBar = document.getElementById('pillar-jit-bar');
  if (jitBar) jitBar.style.width = `${jitScore}%`;

  // 5. DNS Resolution
  let dnsScore = 95;
  setText('pillar-dns-val', `${dnsScore} / 100`);
  const dnsBar = document.getElementById('pillar-dns-bar');
  if (dnsBar) dnsBar.style.width = `${dnsScore}%`;

  // Update Experience Readiness Badges
  // Gaming: heavily depends on Gateway Latency, Jitter, and Loss
  const gamingScore = Math.round((gwScore * 0.5) + (jitScore * 0.3) + (netScore * 0.2));
  setText('readiness-gaming-badge', `${gamingScore}%`);
  setText('readiness-gaming-desc', gamingScore > 85 ? 'Ultra-low router ping, sub-millisecond jitter.' : 'Elevated jitter or latency detected.');

  // Calling: heavily depends on Jitter and Loss
  const callingScore = Math.round((jitScore * 0.6) + (gwScore * 0.4));
  setText('readiness-calls-badge', `${callingScore}%`);
  setText('readiness-calls-desc', callingScore > 90 ? 'Jitter < 1ms, crystal-clear audio/video stream.' : 'Minor packet jitter detected.');

  // Streaming: depends on Physical Link & Loss
  const streamScore = Math.round((sig * 0.6) + (netScore * 0.4));
  setText('readiness-stream-badge', `${streamScore}%`);

  // Web Browsing: depends on DNS & Net
  const webScore = Math.round((dnsScore * 0.5) + (netScore * 0.5));
  setText('readiness-web-badge', `${webScore}%`);
}

// -------------------------------------------------------------
// API: SYSTEM & HARDWARE TELEMETRY
// -------------------------------------------------------------
async function fetchSystemHardware() {
  try {
    const res = await fetch('/api/system-health');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const modelElem = document.getElementById('hw-model-name');
    if (modelElem) {
      if (data.is_raspberry_pi) {
        modelElem.textContent = data.device_model || 'Raspberry Pi 4';
      } else if (data.is_docker) {
        modelElem.textContent = 'Docker Container';
      } else {
        modelElem.textContent = `${data.platform || 'Host'} Appliance`;
      }
    }

    const tempBadge = document.getElementById('hw-temp-badge');
    if (tempBadge) {
      if (data.cpu_temp_c !== null && data.cpu_temp_c !== undefined) {
        tempBadge.textContent = `${data.cpu_temp_c}°C`;
        tempBadge.classList.remove('hidden');
        if (data.cpu_temp_c > 75) tempBadge.className = 'px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 font-mono text-xs';
        else if (data.cpu_temp_c > 60) tempBadge.className = 'px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-mono text-xs';
        else tempBadge.className = 'px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono text-xs';
      } else if (data.cpu_percent !== undefined) {
        tempBadge.textContent = `${data.cpu_percent}% CPU`;
        tempBadge.classList.remove('hidden');
      }
    }
  } catch (err) {
    console.error('Failed to fetch hardware telemetry:', err);
  }
}

// -------------------------------------------------------------
// API: 24/7 HISTORY & INCIDENT LOGS
// -------------------------------------------------------------
async function setHistoryRange(hours, btn) {
  appState.historyHours = hours;
  document.querySelectorAll('.history-range-btn').forEach(b => {
    b.className = 'history-range-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700 transition';
  });
  if (btn) btn.className = 'history-range-btn active px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 text-white transition';
  await fetchHistoryAndIncidents(true);
}

async function fetchHistoryAndIncidents(notify = false) {
  if (notify) showToast('Loading History', 'Fetching persistent 24/7 timeline records...', 'info');

  try {
    const [histRes, incRes] = await Promise.all([
      fetch(`/api/history?hours=${appState.historyHours}`),
      fetch('/api/incidents?limit=30')
    ]);

    if (!histRes.ok) throw new Error(`History HTTP ${histRes.status}`);
    if (!incRes.ok) throw new Error(`Incidents HTTP ${incRes.status}`);

    const history = await histRes.json();
    const incidents = await incRes.json();

    // Calculate Uptime % & Metrics
    const totalSamples = Array.isArray(history) ? history.length : 0;
    let downCount = 0;
    let maxSpike = 0;

    (history || []).forEach(pt => {
      if (pt.is_down) downCount++;
      if (pt.internet_ms && pt.internet_ms > maxSpike) maxSpike = pt.internet_ms;
    });

    const uptimePct = totalSamples > 0 ? (((totalSamples - downCount) / totalSamples) * 100).toFixed(2) : '100.0';
    setText('stat-uptime-percent', `${uptimePct}%`);
    setText('stat-incidents-count', Array.isArray(incidents) ? incidents.length : 0);
    setText('stat-max-spike-ms', maxSpike > 0 ? `${Math.round(maxSpike)} ms` : '-- ms');

    let totalDowntimeSec = 0;
    (incidents || []).forEach(inc => {
      totalDowntimeSec += inc.duration_sec || 0;
    });
    setText('stat-downtime-sec', `${Math.round(totalDowntimeSec)}s`);
    setText('timeline-sample-count', `${totalSamples} samples collected`);

    // Update History Chart safely with downsampling
    updateTimelineChart(history || []);

    // Update Incidents Table
    renderIncidentsTable(incidents || []);

    if (notify) showToast('History Loaded', `Rendered ${totalSamples} continuous telemetry points.`, 'success');
  } catch (err) {
    console.error('History load error:', err);
    const tbody = document.getElementById('incidents-history-tbody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-amber-400">Failed to load telemetry history: ${escapeHtml(err.message)}</td></tr>`;
    }
    if (notify) showToast('History Error', err.message, 'error');
  }
}

// Memory-safe chart update with downsampling for large sample histories
function updateTimelineChart(history) {
  if (!historyChart || !historyChart.data || !historyChart.data.datasets) return;

  const MAX_DISPLAY_POINTS = 300;
  let sampleHistory = history;

  if (history.length > MAX_DISPLAY_POINTS) {
    const step = Math.ceil(history.length / MAX_DISPLAY_POINTS);
    sampleHistory = history.filter((_, idx) => (idx % step === 0) || (idx === history.length - 1));
  }

  const labels = [];
  const internetLatencies = [];
  const gatewayLatencies = [];
  const packetLosses = [];

  sampleHistory.forEach(pt => {
    const d = new Date((pt.timestamp || 0) * 1000);
    const timeLabel = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
    labels.push(timeLabel);
    internetLatencies.push(pt.internet_ms || 0);
    gatewayLatencies.push(pt.gateway_ms || 0);
    packetLosses.push(pt.loss_percent || 0);
  });

  historyChart.data.labels = labels;
  if (historyChart.data.datasets[0]) historyChart.data.datasets[0].data = internetLatencies;
  if (historyChart.data.datasets[1]) historyChart.data.datasets[1].data = gatewayLatencies;
  if (historyChart.data.datasets[2]) historyChart.data.datasets[2].data = packetLosses;
  historyChart.update('none'); // Update without full animation for performance
}

function renderIncidentsTable(incidents) {
  const tbody = document.getElementById('incidents-history-tbody');
  if (!tbody) return;

  if (incidents.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">Zero connection drops recorded! Your link has maintained continuous 100% uptime.</td></tr>`;
    return;
  }

  tbody.innerHTML = incidents.map(inc => {
    const d = new Date((inc.start_time || 0) * 1000);
    const timeStr = `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
    const durStr = inc.duration_sec ? `${inc.duration_sec}s` : 'Active Outage';

    // Format fix advice and action button
    const advice = inc.fix_advice || (
      inc.root_cause && inc.root_cause.includes('ISP')
        ? 'Local Wi-Fi is healthy. Upstream ISP route dropped. Check modem WAN light.'
        : inc.root_cause && inc.root_cause.includes('Driver')
        ? 'Wi-Fi adapter power suspend. Disable Wi-Fi Power Saving.'
        : 'Network drop diagnosed. Flushing DNS & clearing ARP cache.'
    );
    const action = inc.recommended_action || (
      inc.root_cause && inc.root_cause.includes('Driver')
        ? 'fix_power_save'
        : inc.root_cause && inc.root_cause.includes('Gateway')
        ? 'renew_dhcp'
        : 'flush_dns'
    );
    const actionLabel = action === 'fix_power_save'
      ? 'Power Fix'
      : action === 'renew_dhcp'
      ? 'Renew DHCP'
      : action === 'tune_adapter_gaming'
      ? 'Tune Adapter'
      : 'Flush DNS';

    const fixHtml = `
      <div class="flex items-center justify-between gap-2 max-w-sm">
        <span class="text-slate-300 text-[11px] leading-tight line-clamp-2" title="${escapeHtml(advice)}">${escapeHtml(advice)}</span>
        <button onclick="runSingleAction('${escapeHtml(action)}', this)" class="shrink-0 px-2 py-1 bg-cyan-600/30 hover:bg-cyan-600 text-cyan-300 hover:text-white border border-cyan-500/40 rounded-lg text-[10px] font-bold transition active:scale-95 whitespace-nowrap" title="Run recommended fix">
          ${escapeHtml(actionLabel)}
        </button>
      </div>
    `;

    return `
      <tr class="hover:bg-slate-800/40">
        <td class="p-3 font-mono text-slate-300">${escapeHtml(timeStr)}</td>
        <td class="p-3"><span class="px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30">${escapeHtml(inc.incident_type || 'Drop')}</span></td>
        <td class="p-3 font-mono font-bold ${inc.duration_sec ? 'text-amber-400' : 'text-rose-400 animate-pulse'}">${escapeHtml(durStr)}</td>
        <td class="p-3 text-slate-200 font-medium">${escapeHtml(inc.root_cause || 'Network Unreachable')}</td>
        <td class="p-3">${fixHtml}</td>
        <td class="p-3">
          ${inc.auto_healed ? '<span class="px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400">Auto-Resolved</span>' : '<span class="text-slate-500">Manual</span>'}
        </td>
        <td class="p-3">${inc.notified ? '<span class="text-cyan-400">Sent</span>' : '<span class="text-slate-500">Logged</span>'}</td>
      </tr>
    `;
  }).join('');
}

// -------------------------------------------------------------
// API: NOTIFICATIONS & ALERTS CONFIGURATION (MULTI-WEBHOOK)
// -------------------------------------------------------------
function addDiscordWebhookRow(name = '', url = '') {
  const container = document.getElementById('discord-webhooks-container');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'discord-webhook-row p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2 hover:border-slate-700 transition';
  row.innerHTML = `
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 flex-1">
        <span class="discord-row-badge text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-800 text-blue-400 border border-slate-700">#1</span>
        <input type="text" class="discord-name-input bg-slate-800/90 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 w-44" placeholder="Channel (e.g. #ops, #admin)" value="${escapeHtml(name)}">
      </div>
      <div class="flex items-center gap-1.5">
        <button type="button" onclick="testSingleDiscordRow(this)" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-blue-600 hover:text-white text-slate-300 border border-slate-700 text-xs font-semibold flex items-center gap-1 transition active:scale-95" title="Send a test ping to this specific Discord webhook">
          <i data-lucide="send" class="w-3 h-3"></i> Test
        </button>
        <button type="button" onclick="removeDiscordWebhookRow(this)" class="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 border border-transparent hover:border-rose-500/20 transition active:scale-95" title="Remove this webhook">
          <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
        </button>
      </div>
    </div>
    <div class="w-full">
      <input type="url" class="discord-url-input w-full bg-slate-800/90 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-blue-500" placeholder="https://discord.com/api/webhooks/..." value="${escapeHtml(url)}">
    </div>
  `;

  // Attach live counter update when user types URL
  const urlInput = row.querySelector('.discord-url-input');
  if (urlInput) {
    urlInput.addEventListener('input', () => updateDiscordWebhookNumbersAndCounter());
  }

  container.appendChild(row);
  updateDiscordWebhookNumbersAndCounter();
  if (window.lucide) lucide.createIcons();
}

function removeDiscordWebhookRow(btn) {
  const container = document.getElementById('discord-webhooks-container');
  if (!container) return;

  const row = btn.closest('.discord-webhook-row');
  if (!row) return;

  const allRows = container.querySelectorAll('.discord-webhook-row');
  if (allRows.length <= 1) {
    // If it's the only row, just clear input fields instead of removing
    const nameInp = row.querySelector('.discord-name-input');
    const urlInp = row.querySelector('.discord-url-input');
    if (nameInp) nameInp.value = '';
    if (urlInp) urlInp.value = '';
    showToast('Webhook Cleared', 'Cleared webhook fields.', 'info');
  } else {
    row.remove();
  }
  updateDiscordWebhookNumbersAndCounter();
}

function updateDiscordWebhookNumbersAndCounter() {
  const container = document.getElementById('discord-webhooks-container');
  const badge = document.getElementById('discord-webhooks-counter');
  if (!container) return;

  const rows = container.querySelectorAll('.discord-webhook-row');
  let validCount = 0;

  rows.forEach((row, idx) => {
    const badgeSpan = row.querySelector('.discord-row-badge');
    if (badgeSpan) badgeSpan.textContent = `#${idx + 1}`;

    const urlInp = row.querySelector('.discord-url-input');
    if (urlInp && urlInp.value.trim().length > 0) {
      validCount++;
    }
  });

  if (badge) {
    badge.textContent = `${validCount} Configured`;
    if (validCount > 0) {
      badge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30';
    } else {
      badge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-400 border border-slate-700';
    }
  }
}

async function testSingleDiscordRow(btn) {
  const row = btn.closest('.discord-webhook-row');
  if (!row) return;

  const urlInput = row.querySelector('.discord-url-input');
  const url = urlInput ? urlInput.value.trim() : '';

  if (!url) {
    showToast('Missing URL', 'Please paste a Discord Webhook URL before testing.', 'warning');
    if (urlInput) urlInput.focus();
    return;
  }

  if (!url.startsWith('https://discord.com/api/webhooks/') && !url.startsWith('https://discordapp.com/api/webhooks/')) {
    showToast('Invalid URL', 'Discord webhooks must start with https://discord.com/api/webhooks/...', 'warning');
    return;
  }

  const originalContent = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="inline-block animate-spin">&#9696;</span> Testing...`;

  try {
    const res = await fetch('/api/test-discord-single', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ webhook_url: url })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.success) {
      showToast('Discord Ping Success!', data.message, 'success');
      btn.classList.add('bg-emerald-600', 'text-white', 'border-emerald-500');
      btn.innerHTML = `<i data-lucide="check" class="w-3 h-3"></i> Sent!`;
      setTimeout(() => {
        btn.classList.remove('bg-emerald-600', 'text-white', 'border-emerald-500');
        btn.innerHTML = originalContent;
        if (window.lucide) lucide.createIcons();
      }, 2500);
    } else {
      showToast('Discord Test Failed', data.message, 'error');
      btn.innerHTML = originalContent;
    }
  } catch (err) {
    showToast('Network Error', err.message, 'error');
    btn.innerHTML = originalContent;
  } finally {
    btn.disabled = false;
    if (window.lucide) lucide.createIcons();
  }
}

async function loadNotificationSettings() {
  try {
    const res = await fetch('/api/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();

    const winToastEnabled = document.getElementById('setting-windows-toast-enabled');
    if (winToastEnabled) winToastEnabled.checked = s.windows_toast_enabled !== '0';

    const ntfyEnabled = document.getElementById('setting-ntfy-enabled');
    if (ntfyEnabled) ntfyEnabled.checked = s.ntfy_enabled === '1';

    const ntfyTopic = document.getElementById('setting-ntfy-topic');
    if (ntfyTopic) {
      ntfyTopic.value = s.ntfy_topic || 'netpulse-alerts';
      updateNtfyPreview(ntfyTopic.value);
      ntfyTopic.oninput = () => updateNtfyPreview(ntfyTopic.value);
    }

    const discordEnabled = document.getElementById('setting-discord-enabled');
    if (discordEnabled) discordEnabled.checked = s.discord_enabled === '1';

    // Populate multiple Discord webhooks
    const discordContainer = document.getElementById('discord-webhooks-container');
    if (discordContainer) {
      discordContainer.innerHTML = '';
      let webhookList = [];

      if (s.discord_webhooks) {
        try {
          const parsed = typeof s.discord_webhooks === 'string' ? JSON.parse(s.discord_webhooks) : s.discord_webhooks;
          if (Array.isArray(parsed)) {
            webhookList = parsed;
          }
        } catch (e) {
          console.warn('Could not parse discord_webhooks JSON:', e);
        }
      }

      // Fallback to legacy single webhook if array is empty
      if (webhookList.length === 0 && s.discord_webhook) {
        webhookList.push({ name: 'Primary Webhook', url: s.discord_webhook });
      }

      if (webhookList.length > 0) {
        webhookList.forEach(item => {
          if (typeof item === 'object' && item !== null) {
            addDiscordWebhookRow(item.name || '', item.url || '');
          } else if (typeof item === 'string') {
            addDiscordWebhookRow('', item);
          }
        });
      } else {
        // Initial empty row ready for typing
        addDiscordWebhookRow('', '');
      }
      updateDiscordWebhookNumbersAndCounter();
    }

    const telegramEnabled = document.getElementById('setting-telegram-enabled');
    if (telegramEnabled) telegramEnabled.checked = s.telegram_enabled === '1';

    const telegramToken = document.getElementById('setting-telegram-token');
    if (telegramToken) telegramToken.value = s.telegram_bot_token || '';

    const telegramChat = document.getElementById('setting-telegram-chat');
    if (telegramChat) telegramChat.value = s.telegram_chat_id || '';

    const autoHeal = document.getElementById('setting-auto-heal');
    if (autoHeal) autoHeal.checked = s.auto_heal_enabled === '1';

    const alertDrop = document.getElementById('setting-alert-drop');
    if (alertDrop) alertDrop.checked = s.alert_on_drop === '1';

    const alertLatency = document.getElementById('setting-alert-latency');
    if (alertLatency) alertLatency.checked = s.alert_on_high_latency === '1';

  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

function updateNtfyPreview(val) {
  const p = document.getElementById('ntfy-topic-preview');
  if (p) p.textContent = `ntfy.sh/${encodeURIComponent(val || 'netpulse-alerts')}`;
}

async function testWindowsToast(btn) {
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Sending...`;
  try {
    const res = await fetch('/api/test-toast', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Windows Toast Sent', 'Native Windows notification sent with fix advice!', 'success');
    } else {
      showToast('Toast Notice', data.message || 'Toast could not be shown.', 'warning');
    }
  } catch (err) {
    showToast('Toast Error', err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
    if (window.lucide) lucide.createIcons();
  }
}

let isFetchingDaemonStatus = false;
async function fetchDaemonStatus() {
  if (isFetchingDaemonStatus || document.hidden) return;
  isFetchingDaemonStatus = true;
  try {
    const res = await fetch('/api/daemon-status');
    if (!res.ok) return;
    const status = await res.json();
    
    const banner = document.getElementById('live-drop-alert-banner');
    if (!banner) return;

    if (status.status === 'Critical Drop' || (status.fix_advice && status.root_cause)) {
      banner.classList.remove('hidden');
      setText('banner-drop-cause', status.root_cause || 'Connection Drop Detected');
      setText('banner-drop-details', `Gateway: ${Number(status.gateway_ms || 0).toFixed(1)}ms | Internet: ${Number(status.internet_ms || 0).toFixed(1)}ms | Packet Loss: ${status.loss_percent || 100}%`);
      setText('banner-drop-advice', status.fix_advice || 'Running diagnostic analysis...');
      
      const actionBtn = document.getElementById('banner-drop-action-btn');
      if (actionBtn) {
        actionBtn.dataset.action = status.recommended_action || 'flush_dns';
        setText('banner-drop-btn-text', status.action_button || 'Apply Fix Now');
      }
    } else {
      banner.classList.add('hidden');
    }
  } catch (e) {
    // Non-blocking
  } finally {
    isFetchingDaemonStatus = false;
  }
}

function dismissDropBanner() {
  const banner = document.getElementById('live-drop-alert-banner');
  if (banner) banner.classList.add('hidden');
}

async function runBannerFixAction(btn) {
  const action = btn.dataset.action || 'flush_dns';
  await runSingleAction(action, btn);
}

async function saveNotificationSettings(btn) {
  if (btn) btn.disabled = true;
  showToast('Saving', 'Updating alert and auto-heal settings...', 'info');

  // Gather all Discord Webhooks
  const discordRows = document.querySelectorAll('#discord-webhooks-container .discord-webhook-row');
  const webhooksList = [];
  discordRows.forEach((row, idx) => {
    const name = (row.querySelector('.discord-name-input')?.value || '').trim();
    const url = (row.querySelector('.discord-url-input')?.value || '').trim();
    if (url) {
      webhooksList.push({ name: name || `Webhook #${idx + 1}`, url });
    }
  });

  const settings = {
    windows_toast_enabled: getChecked('setting-windows-toast-enabled', true) ? '1' : '0',
    ntfy_enabled: getChecked('setting-ntfy-enabled') ? '1' : '0',
    ntfy_topic: getValue('setting-ntfy-topic', 'netpulse-alerts'),
    discord_enabled: getChecked('setting-discord-enabled') ? '1' : '0',
    discord_webhooks: JSON.stringify(webhooksList),
    discord_webhook: webhooksList.length > 0 ? webhooksList[0].url : '',
    telegram_enabled: getChecked('setting-telegram-enabled') ? '1' : '0',
    telegram_bot_token: getValue('setting-telegram-token'),
    telegram_chat_id: getValue('setting-telegram-chat'),
    auto_heal_enabled: getChecked('setting-auto-heal', true) ? '1' : '0',
    alert_on_drop: getChecked('setting-alert-drop', true) ? '1' : '0',
    alert_on_high_latency: getChecked('setting-alert-latency', true) ? '1' : '0'
  };

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.success) {
      showToast('Settings Saved', `Updated ${webhooksList.length} Discord webhook(s) and alert rules.`, 'success');
      updateDiscordWebhookNumbersAndCounter();
    } else {
      showToast('Save Error', data.message, 'error');
    }
  } catch (err) {
    showToast('Failed to Save', err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function testNotification(btn) {
  if (btn) btn.disabled = true;
  showToast('Dispatching Alert', 'Sending test alert to phone/PC channels...', 'info');

  try {
    const res = await fetch('/api/test-notification', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.success) {
      showToast('Alert Delivered!', data.message, 'success');
    } else {
      showToast('Alert Notice', data.message, 'warning');
    }
  } catch (err) {
    showToast('Test Failed', err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function requestBrowserNotificationPermission(btn) {
  if (!('Notification' in window)) {
    showToast('Not Supported', 'Your browser does not support desktop notifications.', 'warning');
    return;
  }

  Notification.requestPermission().then(permission => {
    if (permission === 'granted') {
      showToast('Permission Granted', 'Desktop push notifications are active.', 'success');
      try {
        new Notification('NetPulse Pro', {
          body: 'Desktop notifications are connected. You will be alerted if connection drops occur.',
          icon: '/static/favicon.ico'
        });
      } catch (e) {}
      if (btn) btn.textContent = 'Desktop Notifications: Enabled';
    } else {
      showToast('Permission Denied', 'Desktop notifications blocked by browser.', 'warning');
    }
  });
}

function updateSpectrumCharts(channels5g, channels24, currentChannel) {
  if (spectrumChart5G && spectrumChart5G.data && spectrumChart5G.data.datasets[0]) {
    const labels = (channels5g || []).map(c => `Ch ${c.channel}${c.is_dfs ? ' (DFS)' : ''}`);
    const data = (channels5g || []).map(c => c.score);
    const colors = (channels5g || []).map(c => {
      if (c.channel === currentChannel) return '#06B6D4';
      if (c.score > 80) return '#10B981';
      if (c.score > 50) return '#F59E0B';
      return '#EF4444';
    });

    spectrumChart5G.data.labels = labels;
    spectrumChart5G.data.datasets[0].data = data;
    spectrumChart5G.data.datasets[0].backgroundColor = colors;
    spectrumChart5G.update('none');
  }

  if (spectrumChart24G && spectrumChart24G.data && spectrumChart24G.data.datasets[0]) {
    const labels = (channels24 || []).map(c => `Ch ${c.channel}`);
    const data = (channels24 || []).map(c => c.score);
    const colors = (channels24 || []).map(c => {
      if (c.channel === currentChannel) return '#06B6D4';
      if ([1, 6, 11].includes(c.channel)) {
        return c.score > 70 ? '#10B981' : '#F59E0B';
      }
      return '#EF4444';
    });

    spectrumChart24G.data.labels = labels;
    spectrumChart24G.data.datasets[0].data = data;
    spectrumChart24G.data.datasets[0].backgroundColor = colors;
    spectrumChart24G.update('none');
  }
}

function updatePingChart(gwTimes, cfTimes, ggTimes) {
  if (!pingChart || !pingChart.data || !pingChart.data.datasets) return;
  const gwArr = Array.isArray(gwTimes) ? gwTimes.slice(0, 30) : [];
  const cfArr = Array.isArray(cfTimes) ? cfTimes.slice(0, 30) : [];
  const ggArr = Array.isArray(ggTimes) ? ggTimes.slice(0, 30) : [];

  const maxSamples = Math.max(gwArr.length, cfArr.length, ggArr.length, 6);
  pingChart.data.labels = Array.from({ length: maxSamples }, (_, i) => `Sample ${i + 1}`);
  if (pingChart.data.datasets[0]) pingChart.data.datasets[0].data = gwArr;
  if (pingChart.data.datasets[1]) pingChart.data.datasets[1].data = cfArr;
  if (pingChart.data.datasets[2]) pingChart.data.datasets[2].data = ggArr;
  pingChart.update('none');
}

function updateDnsChart(ranked) {
  if (!dnsChart || !dnsChart.data || !dnsChart.data.datasets) return;
  const list = Array.isArray(ranked) ? ranked.slice(0, 10) : [];
  dnsChart.data.labels = list.map(r => r.name || 'DNS');
  if (dnsChart.data.datasets[0]) {
    dnsChart.data.datasets[0].data = list.map(r => r.avg_ms || 0);
    dnsChart.data.datasets[0].backgroundColor = list.map((r, i) => i === 0 && r.responsive ? '#10B981' : '#06B6D4');
  }
  dnsChart.update('none');
}

// -------------------------------------------------------------
// TOAST HELPER
// -------------------------------------------------------------
function showToast(title, message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';

  let iconName = 'info';
  let iconColor = 'text-cyan-400';
  if (type === 'success') { iconName = 'check-circle'; iconColor = 'text-emerald-400'; }
  else if (type === 'warning') { iconName = 'alert-triangle'; iconColor = 'text-amber-400'; }
  else if (type === 'error') { iconName = 'x-circle'; iconColor = 'text-rose-400'; }

  toast.innerHTML = `
    <i data-lucide="${iconName}" class="w-5 h-5 ${iconColor} shrink-0"></i>
    <div class="flex-1">
      <div class="text-xs font-bold text-white">${escapeHtml(title)}</div>
      <div class="text-xs text-slate-300 mt-0.5">${escapeHtml(message)}</div>
    </div>
  `;

  container.appendChild(toast);
  initLucide();

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// -------------------------------------------------------------
// API: SECURITY & VULNERABILITY AUDIT
// -------------------------------------------------------------
async function fetchSecurityAudit(notify = false) {
  const btn = document.getElementById('btn-run-security-audit');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Scanning...';
    initLucide();
  }

  try {
    const res = await fetch(`/api/security-audit${notify ? '?force=true' : ''}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    appState.lastSecurityData = data;

    // 1. Update score & grades
    const scoreText = document.getElementById('sec-score-text');
    const gradeText = document.getElementById('sec-grade-text');
    const gradeBadge = document.getElementById('sec-grade-badge');
    const progressBar = document.getElementById('sec-progress-bar');
    const gwTarget = document.getElementById('sec-gateway-target');

    if (scoreText) scoreText.innerText = `${data.score}%`;
    if (gradeText) gradeText.innerText = data.grade;
    if (gwTarget) gwTarget.innerText = data.gateway_ip || 'Auto-detected';

    if (gradeBadge) {
      gradeBadge.innerText = data.grade;
      gradeBadge.className = 'px-3 py-1 rounded-full text-xs font-bold border transition';
      if (data.badge_color === 'rose') {
        gradeBadge.classList.add('bg-rose-500/20', 'text-rose-400', 'border-rose-500/30');
      } else if (data.badge_color === 'amber') {
        gradeBadge.classList.add('bg-amber-500/20', 'text-amber-400', 'border-amber-500/30');
      } else if (data.badge_color === 'blue') {
        gradeBadge.classList.add('bg-blue-500/20', 'text-blue-400', 'border-blue-500/30');
      } else {
        gradeBadge.classList.add('bg-emerald-500/20', 'text-emerald-400', 'border-emerald-500/30');
      }
    }

    if (progressBar) {
      progressBar.style.width = `${data.score}%`;
      progressBar.className = 'h-3 rounded-full transition-all duration-700';
      if (data.score >= 85) progressBar.classList.add('bg-emerald-500');
      else if (data.score >= 70) progressBar.classList.add('bg-cyan-500');
      else if (data.score >= 50) progressBar.classList.add('bg-amber-500');
      else progressBar.classList.add('bg-rose-500');
    }

    // 2. Counters
    const critEl = document.getElementById('sec-critical-count');
    const warnEl = document.getElementById('sec-warning-count');
    const passEl = document.getElementById('sec-passed-count');
    if (critEl) critEl.innerText = data.critical_count;
    if (warnEl) warnEl.innerText = data.warning_count;
    if (passEl) passEl.innerText = data.passed_count;

    // 3. Actionable Fixes Container
    const fixesContainer = document.getElementById('sec-actionable-fixes-container');
    if (fixesContainer) {
      if (!data.actionable_fixes || data.actionable_fixes.length === 0) {
        fixesContainer.innerHTML = `
          <div class="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/30 flex items-center gap-3 text-xs text-emerald-300">
            <i data-lucide="shield-check" class="w-5 h-5 text-emerald-400 shrink-0"></i>
            <div>
              <strong class="text-white">Zero Active Vulnerabilities Found:</strong>
              Your Wi-Fi encryption, gateway router exposure, host firewall, ARP tables, and DNS configuration passed all security defense checks!
            </div>
          </div>
        `;
      } else {
        fixesContainer.innerHTML = data.actionable_fixes.map(fix => {
          const isCritical = fix.severity === 'critical';
          const borderClass = isCritical ? 'border-rose-500/40 bg-rose-950/20' : 'border-amber-500/40 bg-amber-950/20';
          const badgeClass = isCritical ? 'bg-rose-500/20 text-rose-400 border-rose-500/30' : 'bg-amber-500/20 text-amber-400 border-amber-500/30';
          const iconName = isCritical ? 'shield-alert' : 'alert-triangle';
          const btnClass = isCritical ? 'bg-rose-600 hover:bg-rose-500' : 'bg-amber-600 hover:bg-amber-500';

          return `
            <div class="p-4 rounded-xl border ${borderClass} flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div class="flex items-start gap-3">
                <i data-lucide="${iconName}" class="w-5 h-5 shrink-0 mt-0.5 ${isCritical ? 'text-rose-400' : 'text-amber-400'}"></i>
                <div class="space-y-1">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-white">${escapeHtml(fix.title)}</span>
                    <span class="text-[9px] px-2 py-0.5 rounded-full font-bold uppercase border ${badgeClass}">
                      ${escapeHtml(fix.severity)}
                    </span>
                  </div>
                  <p class="text-xs text-slate-300">${escapeHtml(fix.problem)}</p>
                  <p class="text-[11px] text-slate-400 flex items-center gap-1">
                    <i data-lucide="info" class="w-3 h-3 text-cyan-400"></i> ${escapeHtml(fix.recommendation)}
                  </p>
                </div>
              </div>
              ${fix.action && fix.action !== 'none' ? `
                <button onclick="runSecurityFix('${escapeHtml(fix.action)}', this)" class="shrink-0 px-4 py-2 rounded-xl ${btnClass} text-white text-xs font-bold transition active:scale-95 shadow">
                  ${escapeHtml(fix.button_text || 'Fix Vulnerability')}
                </button>
              ` : ''}
            </div>
          `;
        }).join('');
      }
    }

    // 4. 6-Vector Checks Breakdown Grid
    const checksGrid = document.getElementById('sec-checks-grid');
    if (checksGrid && data.checks) {
      checksGrid.innerHTML = data.checks.map(check => {
        let statusBadge = '';
        let iconHtml = '';
        if (check.status === 'passed') {
          statusBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-bold">PASSED</span>';
          iconHtml = '<i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i>';
        } else if (check.status === 'warning') {
          statusBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 font-bold">WARNING</span>';
          iconHtml = '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-400"></i>';
        } else {
          statusBadge = '<span class="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold">CRITICAL</span>';
          iconHtml = '<i data-lucide="x-circle" class="w-4 h-4 text-rose-400"></i>';
        }

        return `
          <div class="glass-panel p-4 flex flex-col justify-between space-y-3">
            <div>
              <div class="flex items-center justify-between">
                <span class="text-[10px] uppercase font-bold text-slate-400 tracking-wider">${escapeHtml(check.category)}</span>
                ${statusBadge}
              </div>
              <h4 class="text-sm font-bold text-white mt-1 flex items-center gap-1.5">
                ${iconHtml} ${escapeHtml(check.name)}
              </h4>
              <p class="text-xs text-slate-300 mt-2 leading-relaxed">
                ${escapeHtml(check.details)}
              </p>
            </div>
            <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400">
              <strong class="text-slate-300">Action:</strong> ${escapeHtml(check.recommendation)}
            </div>
          </div>
        `;
      }).join('');
    }

    initLucide();
    if (notify) showToast('Security Audit Complete', `Assessed 6 vectors. Overall Security Score: ${data.score}% (${data.grade})`, 'info');
  } catch (err) {
    console.error('Security audit error:', err);
    const fixesContainer = document.getElementById('sec-actionable-fixes-container');
    if (fixesContainer) {
      fixesContainer.innerHTML = `
        <div class="p-4 rounded-xl bg-rose-950/20 border border-rose-500/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
          <div class="flex items-center gap-3">
            <i data-lucide="alert-octagon" class="w-5 h-5 text-rose-400 shrink-0"></i>
            <div>
              <strong class="text-rose-300">Security Audit Connection Error:</strong>
              <div class="text-slate-400 mt-0.5">${escapeHtml(err.message || 'Server unreachable')}</div>
            </div>
          </div>
          <button onclick="fetchSecurityAudit(true)" class="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white rounded-lg font-bold shrink-0 transition">
            Retry Scan
          </button>
        </div>
      `;
    }
    const scoreText = document.getElementById('sec-score-text');
    if (scoreText && scoreText.innerText === '--%') scoreText.innerText = 'Err';
    const gradeText = document.getElementById('sec-grade-text');
    if (gradeText) gradeText.innerText = 'Scan error';
    initLucide();
    if (notify) showToast('Security Audit Failed', err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i data-lucide="shield-check" class="w-3.5 h-3.5"></i> Re-Scan Security';
      initLucide();
    }
  }
}

async function runSecurityFix(action, btn) {
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Remediating...';
    initLucide();
  }

  showToast('Applying Security Fix', `Executing 1-click remediation for ${action}...`, 'info');

  try {
    const res = await fetch(`/api/security-fix/${encodeURIComponent(action)}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.success) {
      showToast('Vulnerability Remediated', data.message || 'Fix applied successfully.', 'success');
      await fetchSecurityAudit(false);
    } else {
      showToast('Remediation Incomplete', data.message || 'Could not complete fix.', 'error');
    }
  } catch (err) {
    showToast('Fix Error', err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
      initLucide();
    }
  }
}

// -------------------------------------------------------------
// SECURITY AUDIT REPORT EXPORT
// -------------------------------------------------------------
function exportSecurityReport() {
  const data = appState.lastSecurityData;
  if (!data) {
    showToast('No Audit Data', 'Please run a security audit scan first before exporting.', 'warning');
    return;
  }

  const dateStr = new Date().toLocaleString();
  let md = `# NetPulse Pro - Network Security & Vulnerability Audit Report\n\n`;
  md += `**Generated:** ${dateStr}  \n`;
  md += `**Target Gateway:** \`${data.gateway_ip || 'Auto-detected'}\`  \n`;
  md += `**Overall Security Defense Score:** **${data.score}/100** (${data.grade})  \n`;
  md += `**Critical Risks:** ${data.critical_count} | **Warnings:** ${data.warning_count} | **Passed Checks:** ${data.passed_count}\n\n`;

  md += `## 1. Actionable Findings & Remediations\n\n`;
  if (!data.actionable_fixes || data.actionable_fixes.length === 0) {
    md += `* Zero active vulnerabilities found. All 6 defensive vectors passed verification.\n\n`;
  } else {
    data.actionable_fixes.forEach((fix, idx) => {
      md += `### ${idx + 1}. [${fix.severity.toUpperCase()}] ${fix.title}\n`;
      md += `- **Problem:** ${fix.problem}\n`;
      md += `- **Recommendation:** ${fix.recommendation}\n`;
      if (fix.action && fix.action !== 'none') {
        md += `- **Remediation Action Available:** 1-Click Shield via NetPulse Pro (\`${fix.action}\`)\n`;
      }
      md += `\n`;
    });
  }

  md += `## 2. 6-Vector Defense Breakdown\n\n`;
  if (data.checks) {
    data.checks.forEach(c => {
      md += `### ${c.name} (${c.category})\n`;
      md += `- **Status:** \`${c.status.toUpperCase()}\` (Score deduction: -${c.score_deduction} pts)\n`;
      md += `- **Details:** ${c.details}\n`;
      md += `- **Guidance:** ${c.recommendation}\n\n`;
    });
  }

  md += `---\n*Report generated locally by NetPulse Pro (v2.3.0). Zero external ISP or cloud data transmission.*`;

  // 1. Copy to clipboard
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(md).catch(() => {});
  }

  // 2. Download markdown file
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `netpulse-security-audit-${Date.now()}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast('Security Report Exported', 'Report downloaded (.md) and copied to clipboard.', 'success');
}

// -------------------------------------------------------------
// VERSION CONTROL & SYSTEM UPDATES
// -------------------------------------------------------------
function openVersionModal() {
  const modal = document.getElementById('version-modal');
  if (modal) {
    modal.classList.remove('hidden');
    fetchVersionInfo(false);
    initLucide();
  }
}

function closeVersionModal() {
  const modal = document.getElementById('version-modal');
  if (modal) modal.classList.add('hidden');
}

async function fetchVersionInfo(force = false) {
  try {
    const res = await fetch(`/api/version${force ? '?force=true' : ''}`);
    if (!res.ok) return;
    const data = await res.json();
    appState.versionInfo = data;

    setText('vm-current-ver', `v${data.current_version}`);
    setText('vm-channel', data.channel || 'Stable Pro');
    setText('vm-commit', data.commit || 'main');
    setText('vm-release-date', data.release_date || '2026-10-04');

    // Update version badge in sidebar and header if present
    const sbBadge = document.getElementById('btn-version-badge-text');
    if (sbBadge) sbBadge.innerText = `v${data.current_version}`;
    const hdrBadge = document.getElementById('hdr-version-badge-text');
    if (hdrBadge) hdrBadge.innerText = `v${data.current_version}`;

    const statusBanner = document.getElementById('vm-update-banner');
    const statusText = document.getElementById('vm-status-text');
    if (data.update_info && data.update_info.update_available) {
      if (statusBanner) {
        statusBanner.className = 'p-3 rounded-lg bg-cyan-950/40 border border-cyan-500/40 flex items-center justify-between text-xs text-cyan-300';
      }
      if (statusText) {
        statusText.innerHTML = `<strong>Update Available:</strong> Version v${escapeHtml(data.update_info.latest_version)} is available on GitHub.`;
      }
    } else {
      if (statusBanner) {
        statusBanner.className = 'p-3 rounded-lg bg-emerald-950/30 border border-emerald-500/30 flex items-center gap-2.5 text-xs text-emerald-300';
      }
      if (statusText) {
        statusText.innerText = 'You are running the latest version of NetPulse Pro.';
      }
    }

    // Populate changelog
    const clContainer = document.getElementById('vm-changelog-container');
    if (clContainer && data.changelog) {
      clContainer.innerHTML = data.changelog.map(item => `
        <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-1.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-bold text-white font-mono">v${escapeHtml(item.version)}</span>
              <span class="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${item.tag === 'Latest' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' : 'bg-slate-800 text-slate-400'}">${escapeHtml(item.tag)}</span>
            </div>
            <span class="text-[10px] text-slate-500">${escapeHtml(item.date)}</span>
          </div>
          <ul class="list-disc list-inside space-y-0.5 text-slate-300 text-[11px] leading-relaxed">
            ${(item.changes || []).map(ch => `<li>${escapeHtml(ch)}</li>`).join('')}
          </ul>
        </div>
      `).join('');
    }

    initLucide();
  } catch (err) {
    console.debug('Version fetch error:', err);
  }
}

async function triggerCheckUpdates() {
  const btn = document.getElementById('btn-check-updates-now');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i> Checking...';
    initLucide();
  }

  showToast('Checking Updates', 'Querying GitHub repository for new releases...', 'info');

  try {
    const res = await fetch('/api/check-updates', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    await fetchVersionInfo(false);

    if (data.update_available) {
      showToast('New Update Available!', `NetPulse Pro v${data.latest_version} is available on GitHub.`, 'info');
    } else {
      showToast('Up to Date', `NetPulse Pro v${data.current_version} is the latest release.`, 'success');
    }
  } catch (err) {
    showToast('Update Check', err.message || 'Could not connect to GitHub.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i> Check for Updates';
      initLucide();
    }
  }
}
