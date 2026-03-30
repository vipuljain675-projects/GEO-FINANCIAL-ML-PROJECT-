// --- SENTINEL TACTICAL AUDIO ENGINE ---
class SentinelAudio {
  constructor() {
    this.ctx = null;
    this.masterGain = null;
    this.nodes = [];
    this.initialized = false;
    this.isPlaying = false;
  }

  init() {
    if (this.initialized) return;
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.value = 0.15;
      this.masterGain.connect(this.ctx.destination);
      this.initialized = true;
      console.log("SENTINEL Audio: Tactical Link Active");
    } catch (e) {
      console.warn("Audio Context blocked.");
    }
  }

  // Creates a "Data Center Wind" or "Digital Space" vibe
  createDataWind() {
    const bufferSize = 2 * this.ctx.sampleRate;
    const noiseBuffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
    const output = noiseBuffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
        output[i] = Math.random() * 2 - 1;
    }

    const whiteNoise = this.ctx.createBufferSource();
    whiteNoise.buffer = noiseBuffer;
    whiteNoise.loop = true;

    const filter = this.ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(400, this.ctx.currentTime);
    filter.Q.value = 10;

    const lfo = this.ctx.createOscillator();
    lfo.frequency.value = 0.1;
    const lfoGain = this.ctx.createGain();
    lfoGain.gain.value = 200;
    lfo.connect(lfoGain);
    lfoGain.connect(filter.frequency);

    const gain = this.ctx.createGain();
    gain.gain.value = 0.02; 

    whiteNoise.connect(filter);
    filter.connect(gain);
    gain.connect(this.masterGain);

    whiteNoise.start();
    lfo.start();
    this.nodes.push(whiteNoise, lfo);
  }

  // Creates a "Pulse" that feels alive
  createPulse() {
    const osc1 = this.ctx.createOscillator();
    const osc2 = this.ctx.createOscillator();
    osc1.type = 'sine';
    osc2.type = 'sine';
    osc1.frequency.setValueAtTime(60, this.ctx.currentTime);
    osc2.frequency.setValueAtTime(60.2, this.ctx.currentTime);

    const gain1 = this.ctx.createGain();
    const gain2 = this.ctx.createGain();
    gain1.gain.value = 0.4;
    gain2.gain.value = 0.4;

    osc1.connect(gain1);
    osc2.connect(gain2);
    
    const pulseGain = this.ctx.createGain();
    pulseGain.gain.value = 0.5;
    
    gain1.connect(pulseGain);
    gain2.connect(pulseGain);
    pulseGain.connect(this.masterGain);

    osc1.start();
    osc2.start();
    this.nodes.push(osc1, osc2);
  }

  startDigitalStatic() {
    const blip = () => {
      if (!this.isPlaying) return;
      this.playTactical(Math.random() * 1000 + 500, 0.02, 0.01);
      setTimeout(blip, Math.random() * 5000 + 2000);
    };
    blip();
  }

  startAmbient() {
    if (!this.initialized) this.init();
    if (!this.ctx || this.isPlaying) return;
    this.isPlaying = true;

    this.createDataWind();
    this.createPulse();
    this.startDigitalStatic();
  }

  playTactical(freq = 800, dur = 0.1, vol = 0.05) {
    if (!this.initialized || !this.ctx) this.init();
    if (!this.ctx) return;
    
    const osc = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    osc.type = 'sine'; 
    osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(freq * 0.8, this.ctx.currentTime + dur);
    
    g.gain.setValueAtTime(vol, this.ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + dur);
    
    osc.connect(g);
    g.connect(this.masterGain || this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + dur);
  }
}

window.sentinelAudio = new SentinelAudio();
