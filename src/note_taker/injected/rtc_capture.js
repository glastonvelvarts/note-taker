(function () {
  // Meet plays remote audio via its own NetEQ decoder, not MediaStreamTrack PCM.
  // MediaStreamSource therefore stays silent (peak 0). Capture path:
  //   RTCRtpReceiver.createEncodedStreams → tee → unwrap RED → AudioDecoder(opus) → PCM16@16k
  // Meet forwards the loudest speakers on three fixed streams and names the real speaker in
  // each frame's CSRC, so PCM is buffered and sent per speaker, never mixed.
  if (window.__rtcHooked) return;
  window.__rtcHooked = true;

  const TARGET_RATE = 16000;
  const OPUS_RATE = 48000;
  const FLUSH_SAMPLES = 1600; // 100ms @ 16kHz

  let teedStreams = 0;
  const pcmBuffers = new Map();
  const decoders = new WeakMap();

  function downsample(input, fromRate, toRate) {
    if (fromRate === toRate) return input;
    const ratio = fromRate / toRate;
    const out = new Float32Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) out[i] = input[Math.floor(i * ratio)];
    return out;
  }

  function sendPcm(float32, source) {
    if (!float32.length || !window.send_audio_chunk) return;
    let peak = 0;
    const pcm16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      let s = Math.max(-1, Math.min(1, float32[i]));
      peak = Math.max(peak, Math.abs(s));
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    if (peak < 1e-5) return; // skip digital silence

    const bytes = new Uint8Array(pcm16.buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    window.send_audio_chunk(btoa(binary), source);
  }

  function enqueuePcm(mono, sampleRate, source) {
    const at16 = downsample(mono, sampleRate, TARGET_RATE);
    const pending = pcmBuffers.get(source) || new Float32Array(0);
    let pcmBuf = new Float32Array(pending.length + at16.length);
    pcmBuf.set(pending, 0);
    pcmBuf.set(at16, pending.length);
    while (pcmBuf.length >= FLUSH_SAMPLES) {
      sendPcm(pcmBuf.subarray(0, FLUSH_SAMPLES), source);
      pcmBuf = pcmBuf.slice(FLUSH_SAMPLES);
    }
    pcmBuffers.set(source, pcmBuf);
  }

  // RFC 2198 RED unwrap — Meet wraps Opus as PT=111; RED headers start 0xEF.
  function unwrapRedPayload(data) {
    const u8 = data instanceof Uint8Array ? data : new Uint8Array(data);
    if (u8.length < 5) return null;

    let offset = 0;
    let primaryPT = -1;
    let redundantBytes = 0;
    let redundantHeaders = 0;

    while (offset < u8.length) {
      const first = u8[offset];
      const pt = first & 0x7f;
      if (primaryPT < 0) primaryPT = pt;
      else if (pt !== primaryPT) return null;

      if ((first & 0x80) === 0) {
        if (redundantHeaders === 0) return null;
        offset += 1;
        const primaryStart = offset + redundantBytes;
        if (primaryStart > u8.length) return null;
        return u8.subarray(primaryStart);
      }

      if (offset + 4 > u8.length) return null;
      const blockLen = ((u8[offset + 2] & 0x03) << 8) | u8[offset + 3];
      redundantBytes += blockLen;
      redundantHeaders += 1;
      offset += 4;
    }
    return null;
  }

  function buildDecoder(onPcm, onError) {
    if (typeof AudioDecoder === "undefined" || typeof EncodedAudioChunk === "undefined") {
      console.error("[rtc] AudioDecoder unavailable — cannot decode Meet audio");
      return null;
    }
    const decoder = new AudioDecoder({
      output: (audioData) => {
        try {
          const rate = audioData.sampleRate;
          const frames = audioData.numberOfFrames;
          const channels = audioData.numberOfChannels;
          const left = new Float32Array(frames);
          audioData.copyTo(left, { planeIndex: 0, format: "f32-planar" });
          if (channels > 1) {
            const right = new Float32Array(frames);
            audioData.copyTo(right, { planeIndex: 1, format: "f32-planar" });
            for (let i = 0; i < frames; i++) left[i] = (left[i] + right[i]) * 0.5;
          }
          onPcm(left, rate);
        } finally {
          audioData.close();
        }
      },
      error: (err) => onError(err),
    });
    // Stereo config: Meet sends mono and stereo Opus; stereo decoder handles both.
    decoder.configure({
      codec: "opus",
      sampleRate: OPUS_RATE,
      numberOfChannels: 2,
    });
    return decoder;
  }

  function getDecoderState(track) {
    let state = decoders.get(track);
    if (state) return state;

    state = {
      decoder: null,
      source: 0,
      rebuild() {
        try {
          this.decoder?.close();
        } catch (_) {}
        this.decoder = buildDecoder(
          (mono, rate) => enqueuePcm(mono, rate, this.source),
          (err) => {
            console.warn("[rtc] decoder error", track.id, err && err.message ? err.message : err);
            // rebuild on next frame
            this.decoder = null;
          }
        );
      },
    };
    state.rebuild();
    decoders.set(track, state);
    return state;
  }

  function onEncodedFrame(track, frame) {
    let payload = frame.data;
    const unwrapped = unwrapRedPayload(payload);
    if (unwrapped) payload = unwrapped;

    const state = getDecoderState(track);
    if (!state.decoder) state.rebuild();
    if (!state.decoder) return;

    const meta = frame.getMetadata();
    state.source = meta.contributingSources?.[0] ?? meta.synchronizationSource ?? 0;

    try {
      state.decoder.decode(
        new EncodedAudioChunk({
          type: "key",
          timestamp: frame.timestamp || 0,
          data: payload,
        })
      );
    } catch (err) {
      console.warn("[rtc] decode() threw", track.id, err);
      state.rebuild();
    }
  }

  async function pumpEncodedAudio(track, readable) {
    const reader = readable.getReader();
    track.addEventListener(
      "ended",
      () => {
        reader.cancel().catch(() => {});
      },
      { once: true }
    );
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        onEncodedFrame(track, value);
      }
    } catch (err) {
      console.error("[rtc] encoded tee read error", track.id, err);
    }
  }

  function installEncodedTee() {
    const proto = window.RTCRtpReceiver && window.RTCRtpReceiver.prototype;
    const native = proto && proto.createEncodedStreams;
    if (!proto || typeof native !== "function") {
      console.error(
        "[rtc] createEncodedStreams unavailable — Meet capture will stay silent"
      );
      return;
    }

    proto.createEncodedStreams = function (...args) {
      const streams = native.apply(this, args);
      const track = this.track;
      if (!track || track.kind !== "audio") return streams;

      const [ours, theirs] = streams.readable.tee();
      teedStreams += 1;
      pumpEncodedAudio(track, ours);
      return { readable: theirs, writable: streams.writable };
    };
  }

  // PC hook is a watchdog only (not for PCM): warns when audio is live but never tee'd.
  function installPeerConnectionProbe() {
    const NativePC = window.RTCPeerConnection;
    if (!NativePC) return;

    let watching = false;
    class HookedRTCPeerConnection extends NativePC {
      constructor(...args) {
        super(...args);
        this.addEventListener("track", (e) => {
          if (!e.track || e.track.kind !== "audio") return;
          if (!watching) {
            watching = true;
            setTimeout(() => {
              if (teedStreams === 0) {
                console.error(
                  "[rtc] SILENT CAPTURE: audio tracks live but Meet never called " +
                    "createEncodedStreams (0 tees). Meet may be on RTCRtpScriptTransform."
                );
              }
            }, 8000);
          }
        });
      }
    }
    window.RTCPeerConnection = HookedRTCPeerConnection;
  }

  installEncodedTee();
  installPeerConnectionProbe();
})();
