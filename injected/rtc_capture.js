(function () {
  const TARGET_RATE = 16000;
  const ctx = new AudioContext({ sampleRate: TARGET_RATE });
  console.log("[rtc] AudioContext sampleRate:", ctx.sampleRate, "(target", TARGET_RATE + ")");

  function keepAlive() {
    if (ctx.state !== "running") {
      ctx.resume().then(() => {
        console.log("[rtc] AudioContext state:", ctx.state);
      });
    }
  }
  keepAlive();
  setInterval(keepAlive, 1000);

  const mixBus = ctx.createGain();
  const silence = ctx.createGain();
  silence.gain.value = 0;

  const processor = ctx.createScriptProcessor(4096, 1, 1);
  mixBus.connect(processor);
  processor.connect(silence);
  silence.connect(ctx.destination);

  function downsample(input, fromRate, toRate) {
    if (fromRate === toRate) return input;
    const ratio = fromRate / toRate;
    const out = new Float32Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) out[i] = input[Math.floor(i * ratio)];
    return out;
  }

  let chunkCount = 0;
  let attachedCount = 0;
  processor.onaudioprocess = (e) => {
    keepAlive();
    const input = downsample(e.inputBuffer.getChannelData(0), ctx.sampleRate, TARGET_RATE);
    let peak = 0;
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      let s = Math.max(-1, Math.min(1, input[i]));
      peak = Math.max(peak, Math.abs(s));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const bytes = new Uint8Array(pcm16.buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    chunkCount++;
    if (chunkCount % 25 === 0) {
      console.log(
        "[rtc] chunk",
        chunkCount,
        "tracks",
        attachedCount,
        "peak",
        peak.toFixed(4),
        "ctx",
        ctx.state
      );
    }
    if (window.send_audio_chunk) {
      window.send_audio_chunk(btoa(binary));
    } else if (chunkCount % 25 === 0) {
      console.warn("[rtc] send_audio_chunk not found");
    }
  };

  const attached = new WeakSet();
  function attachTrack(track) {
    if (track.kind !== "audio" || attached.has(track)) return;
    attached.add(track);
    attachedCount++;
    try {
      ctx.createMediaStreamSource(new MediaStream([track])).connect(mixBus);
      console.log("[rtc] attached audio track", track.id, track.readyState, "total", attachedCount);
      keepAlive();
    } catch (err) {
      attachedCount--;
      console.warn("[rtc] attach failed", err);
    }
  }

  const NativePC = window.RTCPeerConnection;
  if (!NativePC) {
    console.warn("[rtc] RTCPeerConnection missing");
    return;
  }

  class HookedRTCPeerConnection extends NativePC {
    constructor(...args) {
      super(...args);
      console.log("[rtc] RTCPeerConnection created");
      this.addEventListener("track", (e) => attachTrack(e.track));
      // tracks may already be present when the event was missed
      try {
        for (const receiver of this.getReceivers()) {
          if (receiver.track) attachTrack(receiver.track);
        }
      } catch (_) {}
    }
  }
  window.RTCPeerConnection = HookedRTCPeerConnection;
  window.__rtcHooked = true;
  console.log("[rtc] RTCPeerConnection hooked");
})();
