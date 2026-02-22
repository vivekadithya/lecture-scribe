/**
 * LectureScribe — AudioWorklet Processor
 * 
 * Runs on the audio rendering thread. Accumulates PCM samples
 * into a ring buffer and posts 2-second chunks to the main thread.
 */

class PCMExtractorProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        const bufferDuration = options?.processorOptions?.bufferDurationSec || 2;
        this.bufferSize = Math.floor(sampleRate * bufferDuration);
        this.buffer = new Float32Array(this.bufferSize);
        this.writeIndex = 0;
    }

    process(inputs, outputs) {
        const input = inputs[0];
        if (!input || input.length === 0) return true;

        // Take the first channel (mono)
        const channelData = input[0];
        if (!channelData || channelData.length === 0) return true;

        // Also pass audio through to output (keep tab audio audible)
        const output = outputs[0];
        if (output && output.length > 0) {
            for (let ch = 0; ch < output.length; ch++) {
                if (input[ch]) {
                    output[ch].set(input[ch]);
                }
            }
        }

        // Accumulate samples into the buffer
        for (let i = 0; i < channelData.length; i++) {
            this.buffer[this.writeIndex] = channelData[i];
            this.writeIndex++;

            // When buffer is full, send it to the main thread
            if (this.writeIndex >= this.bufferSize) {
                this.port.postMessage({
                    audioData: new Float32Array(this.buffer)
                });
                this.writeIndex = 0;
            }
        }

        return true; // Keep processor alive
    }
}

registerProcessor('pcm-extractor', PCMExtractorProcessor);
