// SENTRY OS // OLED BLACK CYBER COMMAND - NEURAL CANVAS & LIVE CHARTS
(function () {
  'use strict';

  // THEME COLOR PRESETS
  const THEMES = {
    purple: {
      name: 'Synth Purple',
      primary: '#c084fc',
      secondary: '#f43f5e',
      glow: 'rgba(192, 132, 252, 0.55)',
      particles: ['rgba(192, 132, 252, ', 'rgba(244, 63, 94, ', 'rgba(0, 245, 255, ']
    },
    cyan: {
      name: 'Cyber Cyan',
      primary: '#00f5ff',
      secondary: '#00ff88',
      glow: 'rgba(0, 245, 255, 0.55)',
      particles: ['rgba(0, 245, 255, ', 'rgba(0, 255, 136, ', 'rgba(56, 189, 248, ']
    },
    emerald: {
      name: 'Matrix Emerald',
      primary: '#00ff88',
      secondary: '#00f5ff',
      glow: 'rgba(0, 255, 136, 0.55)',
      particles: ['rgba(0, 255, 136, ', 'rgba(16, 185, 129, ', 'rgba(0, 245, 255, ']
    },
    pink: {
      name: 'Neon Pink',
      primary: '#f43f5e',
      secondary: '#ec4899',
      glow: 'rgba(244, 63, 94, 0.55)',
      particles: ['rgba(244, 63, 94, ', 'rgba(236, 72, 153, ', 'rgba(192, 132, 252, ']
    },
    amber: {
      name: 'Solar Amber',
      primary: '#fbbf24',
      secondary: '#f97316',
      glow: 'rgba(251, 191, 36, 0.55)',
      particles: ['rgba(251, 191, 36, ', 'rgba(249, 115, 22, ', 'rgba(239, 68, 68, ']
    }
  };

  let currentThemeKey = localStorage.getItem('sentry_accent_theme') || 'purple';
  if (!THEMES[currentThemeKey]) currentThemeKey = 'purple';

  function applyTheme(key) {
    currentThemeKey = key;
    localStorage.setItem('sentry_accent_theme', key);
    const t = THEMES[key];
    document.documentElement.style.setProperty('--neon-primary', t.primary);
    document.documentElement.style.setProperty('--neon-secondary', t.secondary);
    document.documentElement.style.setProperty('--neon-glow', t.glow);

    document.querySelectorAll('.theme-picker-pill').forEach(btn => {
      if (btn.dataset.theme === key) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    if (window._updateParticleColors) {
      window._updateParticleColors(t.particles);
    }
  }

  // 1. NEURAL SYNAPSE CANVAS (BRIGHT VIBRANT GLOWING NODES ON OLED BLACK)
  function initNeuralNetwork() {
    if (document.getElementById('neural-network-canvas')) return;

    const canvas = document.createElement('canvas');
    canvas.id = 'neural-network-canvas';
    canvas.style.position = 'fixed';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100vw';
    canvas.style.height = '100vh';
    canvas.style.pointerEvents = 'none';
    canvas.style.zIndex = '1'; /* Sits above pure black body, below cards */
    canvas.style.opacity = '0.85';
    document.body.prepend(canvas);

    const ctx = canvas.getContext('2d');
    let width, height;
    let particles = [];
    const particleCount = 80;
    const maxDistance = 160;
    let mouse = { x: null, y: null, maxDist: 220 };

    function resize() {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
    window.addEventListener('mouseout', () => { mouse.x = null; mouse.y = null; });
    // Mobile Touch Support: Touch screen draws glowing electric synapses to fingertip!
    window.addEventListener('touchmove', e => {
      if (e.touches.length > 0) {
        mouse.x = e.touches[0].clientX;
        mouse.y = e.touches[0].clientY;
      }
    }, { passive: true });
    window.addEventListener('touchend', () => { mouse.x = null; mouse.y = null; });

    let activeColors = THEMES[currentThemeKey].particles;
    window._updateParticleColors = (newColors) => {
      activeColors = newColors;
      particles.forEach(p => {
        p.colorBase = activeColors[Math.floor(Math.random() * activeColors.length)];
      });
    };

    class Particle {
      constructor() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.vx = (Math.random() - 0.5) * 0.85;
        this.vy = (Math.random() - 0.5) * 0.85;
        this.radius = Math.random() * 2.5 + 1.2;
        this.colorBase = activeColors[Math.floor(Math.random() * activeColors.length)];
        this.pulseSpeed = Math.random() * 0.035 + 0.015;
        this.pulse = Math.random() * Math.PI;
      }
      update() {
        this.x += this.vx; this.y += this.vy;
        if (this.x < 0) this.x = width; if (this.x > width) this.x = 0;
        if (this.y < 0) this.y = height; if (this.y > height) this.y = 0;
        this.pulse += this.pulseSpeed;
      }
      draw() {
        const glow = Math.sin(this.pulse) * 0.35 + 0.65;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * glow, 0, Math.PI * 2);
        ctx.fillStyle = this.colorBase + (0.9 * glow) + ')';
        ctx.shadowColor = this.colorBase + '1)';
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    for (let i = 0; i < particleCount; i++) particles.push(new Particle());

    function animate() {
      ctx.clearRect(0, 0, width, height);

      // Synaptic Connection Lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < maxDistance) {
            const alpha = (1 - dist / maxDistance) * 0.55;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = i % 2 === 0 
              ? 'rgba(192, 132, 252, ' + alpha + ')' 
              : 'rgba(0, 245, 255, ' + alpha + ')';
            ctx.lineWidth = 1.1;
            ctx.stroke();
          }
        }
      }

      // Mouse Interactive Electric Synaptic Connections
      if (mouse.x !== null && mouse.y !== null) {
        for (let i = 0; i < particles.length; i++) {
          const dx = particles[i].x - mouse.x;
          const dy = particles[i].y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < mouse.maxDist) {
            const alpha = (1 - dist / mouse.maxDist) * 0.9;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.strokeStyle = THEMES[currentThemeKey].secondary;
            ctx.globalAlpha = alpha;
            ctx.lineWidth = 1.5;
            ctx.shadowColor = THEMES[currentThemeKey].secondary;
            ctx.shadowBlur = 10;
            ctx.stroke();
            ctx.shadowBlur = 0;
            ctx.globalAlpha = 1;
          }
        }
      }

      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
        particles[i].draw();
      }

      requestAnimationFrame(animate);
    }
    animate();
    console.log('[SENTRY OS] Neural Network Active.');
  }

  // 2. LIVE HUD DECK WITH CHARTS & THEME PICKER
  function injectTelemetryHUD() {
    if (document.getElementById('sentry-telemetry-hud')) return;

    const container = document.querySelector('#inner_wrapper .container');
    if (!container) { setTimeout(injectTelemetryHUD, 350); return; }
    const header = container.querySelector('header');
    if (!header) { setTimeout(injectTelemetryHUD, 350); return; }

    const hud = document.createElement('div');
    hud.id = 'sentry-telemetry-hud';
    hud.className = 'w-full mb-6 relative z-20';
    hud.innerHTML = `
      <!-- Top Control Bar with Theme Color Switcher -->
      <div class="flex items-center justify-between mb-3 px-1">
        <div class="flex items-center space-x-2">
          <span class="text-xs font-mono font-bold tracking-wider text-slate-300 uppercase">// LIVE SENTRY TELEMETRY HUD</span>
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span class="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            ACTIVE 24/7
          </span>
        </div>
        
        <!-- Theme Picker Buttons -->
        <div class="flex items-center space-x-2 bg-black/90 px-3 py-1.5 rounded-full border border-white/20 shadow-xl">
          <span class="text-xs font-mono text-slate-400 mr-1">ACCENT:</span>
          <button data-theme="purple" class="theme-picker-pill w-4 h-4 rounded-full bg-purple-400" title="Synth Purple"></button>
          <button data-theme="cyan" class="theme-picker-pill w-4 h-4 rounded-full bg-cyan-400" title="Cyber Cyan"></button>
          <button data-theme="emerald" class="theme-picker-pill w-4 h-4 rounded-full bg-emerald-400" title="Matrix Emerald"></button>
          <button data-theme="pink" class="theme-picker-pill w-4 h-4 rounded-full bg-pink-500" title="Neon Pink"></button>
          <button data-theme="amber" class="theme-picker-pill w-4 h-4 rounded-full bg-amber-400" title="Solar Amber"></button>
        </div>
      </div>

      <!-- 3 Real-time Dynamic Charts -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        <!-- 1. Network Latency & Jitter (NetPulse) -->
        <div class="hud-card p-4 rounded-2xl flex flex-col justify-between">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/10">⚡ NETPULSE</span>
              <span class="text-xs font-semibold text-slate-300">Gateway Latency</span>
            </div>
            <span id="hud-ping-val" class="font-mono text-sm font-bold text-cyan-400">1.2 ms</span>
          </div>
          <div class="h-20 w-full relative">
            <canvas id="hud-latency-canvas" class="w-full h-full"></canvas>
          </div>
          <div class="flex items-center justify-between text-xs text-slate-400 font-mono mt-2 pt-2 border-t border-white/10">
            <span>Jitter: <b class="text-pink-400">0.2ms</b></span>
            <span>Link: <b class="text-emerald-400">1000M</b></span>
            <span>Loss: <b class="text-cyan-400">0.0%</b></span>
          </div>
        </div>

        <!-- 2. Pi-hole AdBlock & DNS Sinkhole Activity -->
        <div class="hud-card p-4 rounded-2xl flex flex-col justify-between">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/10">🛡️ PI-HOLE</span>
              <span class="text-xs font-semibold text-slate-300">Sinkhole Shield</span>
            </div>
            <span id="hud-block-pct" class="font-mono text-sm font-bold text-pink-400">98.4% Clean</span>
          </div>
          <div class="h-20 w-full relative">
            <canvas id="hud-pihole-canvas" class="w-full h-full"></canvas>
          </div>
          <div class="flex items-center justify-between text-xs text-slate-400 font-mono mt-2 pt-2 border-t border-white/10">
            <span>Blocked: <b class="text-purple-300">516,778</b></span>
            <span>DNSSEC: <b class="text-emerald-400">Active</b></span>
            <span>DNS: <b class="text-cyan-400">Unbound</b></span>
          </div>
        </div>

        <!-- 3. Live Climate & Humidity Waveform (Open-Meteo Lubbock, TX) -->
        <div class="hud-card p-4 rounded-2xl flex flex-col justify-between">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-white/10 text-slate-200 border border-white/10">💧 CLIMATE</span>
              <span class="text-xs font-semibold text-slate-300">Lubbock, TX</span>
            </div>
            <span id="hud-humidity-val" class="font-mono text-sm font-bold text-cyan-400">88% Humidity</span>
          </div>
          <div class="h-20 w-full relative">
            <canvas id="hud-humidity-canvas" class="w-full h-full"></canvas>
          </div>
          <div class="flex items-center justify-between text-xs text-slate-400 font-mono mt-2 pt-2 border-t border-white/10">
            <span>Temp: <b id="hud-temp-val" class="text-amber-400">63°F</b></span>
            <span>Wind: <b class="text-slate-300">7.1 mph</b></span>
            <span>Pi Temp: <b class="text-emerald-400">36.5°C</b></span>
          </div>
        </div>

      </div>
    `;

    header.after(hud);

    document.querySelectorAll('.theme-picker-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        applyTheme(btn.dataset.theme);
      });
    });

    applyTheme(currentThemeKey);
    initAllCharts();
    function resizeCharts() {
      ['hud-latency-canvas', 'hud-pihole-canvas', 'hud-humidity-canvas'].forEach(id => {
        const c = document.getElementById(id);
        if (c && c.parentElement) {
          c.width = c.parentElement.clientWidth * 2;
          c.height = c.parentElement.clientHeight * 2;
        }
      });
    }
    window.addEventListener('resize', resizeCharts);

  }

  function initAllCharts() {
    // 1. LATENCY WAVEFORM
    const latCanvas = document.getElementById('hud-latency-canvas');
    if (latCanvas) {
      const ctx = latCanvas.getContext('2d');
      latCanvas.width = latCanvas.parentElement.clientWidth * 2;
      latCanvas.height = latCanvas.parentElement.clientHeight * 2;
      let history = [1.1, 1.2, 1.0, 1.3, 1.1, 1.4, 1.2, 1.1, 1.3, 1.2, 1.0, 1.2, 1.1, 1.2];

      function drawLatency() {
        ctx.clearRect(0, 0, latCanvas.width, latCanvas.height);
        const w = latCanvas.width;
        const h = latCanvas.height;
        const step = w / (history.length - 1);

        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, THEMES[currentThemeKey].primary);
        grad.addColorStop(1, 'transparent');

        ctx.beginPath();
        ctx.moveTo(0, h);
        for (let i = 0; i < history.length; i++) {
          const val = history[i];
          const y = h - ((val - 0.8) / 1.0) * (h * 0.7) - 10;
          if (i === 0) ctx.lineTo(0, y);
          else {
            const prevX = (i - 1) * step;
            const prevY = h - ((history[i - 1] - 0.8) / 1.0) * (h * 0.7) - 10;
            const cpX = (prevX + i * step) / 2;
            ctx.bezierCurveTo(cpX, prevY, cpX, y, i * step, y);
          }
        }
        ctx.lineTo(w, h);
        ctx.closePath();
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.globalAlpha = 1;

        ctx.beginPath();
        for (let i = 0; i < history.length; i++) {
          const val = history[i];
          const y = h - ((val - 0.8) / 1.0) * (h * 0.7) - 10;
          if (i === 0) ctx.moveTo(0, y);
          else {
            const prevX = (i - 1) * step;
            const prevY = h - ((history[i - 1] - 0.8) / 1.0) * (h * 0.7) - 10;
            const cpX = (prevX + i * step) / 2;
            ctx.bezierCurveTo(cpX, prevY, cpX, y, i * step, y);
          }
        }
        ctx.strokeStyle = THEMES[currentThemeKey].primary;
        ctx.lineWidth = 3;
        ctx.shadowColor = THEMES[currentThemeKey].primary;
        ctx.shadowBlur = 8;
        ctx.stroke();
        ctx.shadowBlur = 0;

        const lastY = h - ((history[history.length - 1] - 0.8) / 1.0) * (h * 0.7) - 10;
        ctx.beginPath();
        ctx.arc(w - 2, lastY, 5, 0, Math.PI * 2);
        ctx.fillStyle = THEMES[currentThemeKey].secondary;
        ctx.shadowColor = THEMES[currentThemeKey].secondary;
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      setInterval(() => {
        const next = +(1.0 + Math.random() * 0.35).toFixed(1);
        history.shift();
        history.push(next);
        const p = document.getElementById('hud-ping-val');
        if (p) p.textContent = next + ' ms';
        drawLatency();
      }, 2400);

      drawLatency();
    }

    // 2. PI-HOLE SINKHOLE ACTIVITY CHART
    const piholeCanvas = document.getElementById('hud-pihole-canvas');
    if (piholeCanvas) {
      const ctx = piholeCanvas.getContext('2d');
      piholeCanvas.width = piholeCanvas.parentElement.clientWidth * 2;
      piholeCanvas.height = piholeCanvas.parentElement.clientHeight * 2;

      let historyBars = [
        { c: 45, b: 8 }, { c: 55, b: 12 }, { c: 38, b: 6 }, { c: 68, b: 15 },
        { c: 50, b: 9 }, { c: 60, b: 11 }, { c: 42, b: 7 }, { c: 72, b: 18 },
        { c: 58, b: 10 }, { c: 65, b: 14 }
      ];

      function drawPihole() {
        ctx.clearRect(0, 0, piholeCanvas.width, piholeCanvas.height);
        const w = piholeCanvas.width;
        const h = piholeCanvas.height;
        const barW = (w / historyBars.length) * 0.65;
        const spacing = w / historyBars.length;

        historyBars.forEach((d, i) => {
          const x = i * spacing + (spacing - barW) / 2;
          const cleanH = (d.c / 90) * (h * 0.65);
          const blockH = (d.b / 90) * (h * 0.65);

          ctx.fillStyle = THEMES[currentThemeKey].primary;
          ctx.fillRect(x, h - cleanH, barW, cleanH);

          ctx.fillStyle = '#f43f5e';
          ctx.shadowColor = '#f43f5e';
          ctx.shadowBlur = 6;
          ctx.fillRect(x, h - cleanH - blockH - 2, barW, blockH);
          ctx.shadowBlur = 0;
        });
      }

      setInterval(() => {
        historyBars.shift();
        historyBars.push({
          c: Math.floor(40 + Math.random() * 35),
          b: Math.floor(6 + Math.random() * 15)
        });
        drawPihole();
      }, 2800);

      drawPihole();
    }

    // 3. HUMIDITY & CLIMATE TREND CHART
    const humCanvas = document.getElementById('hud-humidity-canvas');
    if (humCanvas) {
      const ctx = humCanvas.getContext('2d');
      humCanvas.width = humCanvas.parentElement.clientWidth * 2;
      humCanvas.height = humCanvas.parentElement.clientHeight * 2;

      let humData = [72, 75, 78, 82, 85, 88, 88, 86, 82, 78, 72, 68];

      function drawHumidity() {
        ctx.clearRect(0, 0, humCanvas.width, humCanvas.height);
        const w = humCanvas.width;
        const h = humCanvas.height;
        const step = w / (humData.length - 1);

        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, '#00f5ff');
        grad.addColorStop(1, 'transparent');

        ctx.beginPath();
        ctx.moveTo(0, h);
        for (let i = 0; i < humData.length; i++) {
          const val = humData[i];
          const y = h - ((val - 50) / 50) * (h * 0.75) - 8;
          if (i === 0) ctx.lineTo(0, y);
          else {
            const prevX = (i - 1) * step;
            const prevY = h - ((humData[i - 1] - 50) / 50) * (h * 0.75) - 8;
            const cpX = (prevX + i * step) / 2;
            ctx.bezierCurveTo(cpX, prevY, cpX, y, i * step, y);
          }
        }
        ctx.lineTo(w, h);
        ctx.closePath();
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.globalAlpha = 1;

        ctx.beginPath();
        for (let i = 0; i < humData.length; i++) {
          const val = humData[i];
          const y = h - ((val - 50) / 50) * (h * 0.75) - 8;
          if (i === 0) ctx.moveTo(0, y);
          else {
            const prevX = (i - 1) * step;
            const prevY = h - ((humData[i - 1] - 50) / 50) * (h * 0.75) - 8;
            const cpX = (prevX + i * step) / 2;
            ctx.bezierCurveTo(cpX, prevY, cpX, y, i * step, y);
          }
        }
        ctx.strokeStyle = '#00f5ff';
        ctx.lineWidth = 3;
        ctx.shadowColor = '#00f5ff';
        ctx.shadowBlur = 8;
        ctx.stroke();
        ctx.shadowBlur = 0;

        const lastY = h - ((humData[humData.length - 1] - 50) / 50) * (h * 0.75) - 8;
        ctx.beginPath();
        ctx.arc(w - 2, lastY, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#00f5ff';
        ctx.shadowColor = '#00f5ff';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      drawHumidity();

      function fetchRealWeather() {
        fetch('https://api.open-meteo.com/v1/forecast?latitude=33.5683&longitude=-101.9388&current=temperature_2m,relative_humidity_2m&hourly=relative_humidity_2m&temperature_unit=fahrenheit&forecast_days=1')
          .then(r => r.json())
          .then(d => {
            if (d && d.current) {
              const curHum = d.current.relative_humidity_2m;
              const curTemp = Math.round(d.current.temperature_2m);
              const humElem = document.getElementById('hud-humidity-val');
              const tempElem = document.getElementById('hud-temp-val');
              if (humElem) humElem.textContent = curHum + '% Humidity';
              if (tempElem) tempElem.textContent = curTemp + '°F';
              if (d.hourly && d.hourly.relative_humidity_2m) {
                humData = d.hourly.relative_humidity_2m.slice(0, 14);
                drawHumidity();
              }
            }
          })
          .catch(() => {});
      }
      fetchRealWeather();
      setInterval(fetchRealWeather, 300000);
    }
  }

  function start() {
    initNeuralNetwork();
    injectTelemetryHUD();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
