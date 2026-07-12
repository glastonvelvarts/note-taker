(function () {
  const ctx = new AudioContext({ sampleRate: 16000 });
  ctx.resume();

  const mixBus = ctx.createGain();
  const silence = ctx.createGain();
  silence.gain.value = 0;

  const processor = ctx.createScriptProcessor(4096, 1, 1);
  mixBus.connect(processor);
  processor.connect(silence);
  silence.connect(ctx.destination);

  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    const pcm16 = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      let s = Math.max(-1, Math.min(1, input[i]));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const bytes = new Uint8Array(pcm16.buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    chunkCount++;
    if (chunkCount % 25 ===0){
      console.log("[rtc] sending audio chunk", chunkCount);
    }
    if (window.send_audio_chunk) {
      window.send_audio_chunk(btoa(binary));
    }else{
      console.warn("[rtc] send_audio_chunk not found");
    }
  };

  const attached = new Set();
  function attachTrack(track) {
    if (track.kind !== "audio" || attached.has(track)) return;
    attached.add(track);
    try {
      ctx.createMediaStreamSource(new MediaStream([track])).connect(mixBus);
      console.log("[rtc] attached audio track", track.id);
    } catch (err) {
      attached.delete(track);
      console.warn("[rtc] attach failed", err);
    }
  }

  const NativePC = window.RTCPeerConnection;
  if (!NativePC) return;

  window.RTCPeerConnection = function (...args) {
    const pc = new NativePC(...args);
    pc.addEventListener("track", (e) => attachTrack(e.track));
    return pc;
  };
  window.RTCPeerConnection.prototype = NativePC.prototype;
})();
