import Foundation
import Metal
import MetalPerformanceShaders

/// gpu-z's measurements, straight on Metal: the device's own description,
/// and four benchmarks timed by the GPU itself (`gpuStartTime` to
/// `gpuEndTime` of each command buffer), so no CPU↔GPU copy and no torch
/// import is in the number. The terminal's `gpu-z` (offlinai_bench in
/// python-ios-lib) reaches them through `ctypes.CDLL(None)`, and
/// `_cbGPUBenchKeepAlive`, called from ManimStudioApp's init, keeps them in
/// the Release binary. The same code as CodeBench's GPUBench.swift, apart
/// from `nonisolated` (this target's code is main-actor by default, and
/// Python calls these from its own threads).
///
/// The kernels are compiled from source at first use
/// (`MTLDevice.makeLibrary(source:)`): Metal Shading Language, which the
/// public API compiles on the device.

nonisolated private enum GPUBench {
    static let device: MTLDevice? = MTLCreateSystemDefaultDevice()
    static let queue: MTLCommandQueue? = device?.makeCommandQueue()

    static let source = """
    #include <metal_stdlib>
    using namespace metal;

    // Eight independent fused multiply-add chains a thread, four lanes each:
    // 64 flops an iteration. x = x·m + c converges, so nothing overflows.
    kernel void cb_fma32(device float4 *out [[buffer(0)]],
                         constant uint &iters [[buffer(1)]],
                         uint gid [[thread_position_in_grid]]) {
        float4 m = float4(0.9999f), c = float4(1e-5f);
        float4 a0 = float4(float(gid & 7u) * 0.01f + 1.0f);
        float4 a1 = a0 + 0.1f, a2 = a0 + 0.2f, a3 = a0 + 0.3f;
        float4 a4 = a0 + 0.4f, a5 = a0 + 0.5f, a6 = a0 + 0.6f, a7 = a0 + 0.7f;
        for (uint i = 0; i < iters; i++) {
            a0 = fma(a0, m, c); a1 = fma(a1, m, c); a2 = fma(a2, m, c); a3 = fma(a3, m, c);
            a4 = fma(a4, m, c); a5 = fma(a5, m, c); a6 = fma(a6, m, c); a7 = fma(a7, m, c);
        }
        out[gid] = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;
    }

    kernel void cb_fma16(device half4 *out [[buffer(0)]],
                         constant uint &iters [[buffer(1)]],
                         uint gid [[thread_position_in_grid]]) {
        half4 m = half4(0.999h), c = half4(0.001h);
        half4 a0 = half4(half(gid & 7u) * 0.01h + 1.0h);
        half4 a1 = a0 + 0.1h, a2 = a0 + 0.2h, a3 = a0 + 0.3h;
        half4 a4 = a0 + 0.4h, a5 = a0 + 0.5h, a6 = a0 + 0.6h, a7 = a0 + 0.7h;
        for (uint i = 0; i < iters; i++) {
            a0 = fma(a0, m, c); a1 = fma(a1, m, c); a2 = fma(a2, m, c); a3 = fma(a3, m, c);
            a4 = fma(a4, m, c); a5 = fma(a5, m, c); a6 = fma(a6, m, c); a7 = fma(a7, m, c);
        }
        out[gid] = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;
    }

    // A copy, 16 bytes a thread: memory bandwidth, nothing else.
    kernel void cb_copy(device const float4 *src [[buffer(0)]],
                        device float4 *dst [[buffer(1)]],
                        uint gid [[thread_position_in_grid]]) {
        dst[gid] = src[gid];
    }
    """

    static let library: MTLLibrary? = {
        guard let device else { return nil }
        return try? device.makeLibrary(source: source, options: nil)
    }()

    static func pipeline(_ name: String) -> MTLComputePipelineState? {
        guard let device, let function = library?.makeFunction(name: name) else { return nil }
        return try? device.makeComputePipelineState(function: function)
    }

    /// The GPU's own time for `encode`'s work, the best of the command
    /// buffers that fit in `ms` (at least two: the first wakes the GPU).
    static func time(ms: Int32, _ encode: (MTLCommandBuffer) -> Bool) -> Double {
        guard let queue else { return 0 }
        var best = Double.infinity
        let deadline = Date().addingTimeInterval(Double(max(ms, 50)) / 1000)
        var runs = 0
        repeat {
            guard let buffer = queue.makeCommandBuffer(), encode(buffer) else { return 0 }
            buffer.commit()
            buffer.waitUntilCompleted()
            if buffer.status != .completed { return 0 }
            let gpu = buffer.gpuEndTime - buffer.gpuStartTime
            if runs > 0, gpu > 0 { best = min(best, gpu) }
            runs += 1
        } while runs < 3 || Date() < deadline
        return best.isFinite ? best : 0
    }
}

/// The device as Metal describes it, as JSON into `buffer` (NUL-terminated,
/// at most `capacity` bytes). Returns the length written, or -1.
@_cdecl("cb_gpu_info_json")
public nonisolated func cb_gpu_info_json(_ buffer: UnsafeMutablePointer<CChar>?, _ capacity: Int32) -> Int32 {
    guard let buffer, capacity > 1, let device = GPUBench.device else { return -1 }
    // The families by their raw values: an SDK that does not name a newer
    // one still asks the device about it.
    let families: [(String, Int)] = [
        ("Apple1", 1001), ("Apple2", 1002), ("Apple3", 1003), ("Apple4", 1004), ("Apple5", 1005),
        ("Apple6", 1006), ("Apple7", 1007), ("Apple8", 1008), ("Apple9", 1009), ("Apple10", 1010),
        ("Mac2", 2002), ("Common1", 3001), ("Common2", 3002), ("Common3", 3003),
        ("Metal3", 5001), ("Metal4", 5002),
    ]
    let supported = families.filter { _, raw in
        MTLGPUFamily(rawValue: raw).map { device.supportsFamily($0) } ?? false
    }.map(\.0)
    let threads = device.maxThreadsPerThreadgroup
    var info: [String: Any] = [
        "name": device.name,
        "registry_id": device.registryID,
        "unified_memory": device.hasUnifiedMemory,
        "budget": device.recommendedMaxWorkingSetSize,
        "max_buffer": device.maxBufferLength,
        "allocated": device.currentAllocatedSize,
        "max_threads_per_group": [threads.width, threads.height, threads.depth],
        "threadgroup_memory": device.maxThreadgroupMemoryLength,
        "families": supported,
        "raytracing": device.supportsRaytracing,
        "function_pointers": device.supportsFunctionPointers,
        "dynamic_libraries": device.supportsDynamicLibraries,
        "argument_buffers_tier": device.argumentBuffersSupport.rawValue + 1,
        "read_write_textures_tier": device.readWriteTextureSupport.rawValue,
        "float32_filtering": device.supports32BitFloatFiltering,
        "bc_textures": device.supportsBCTextureCompression,
        "barycentrics": device.supportsShaderBarycentricCoordinates,
        "sparse_tile_bytes": device.sparseTileSizeInBytes,
    ]
    if let library = GPUBench.library {
        info["kernels_compiled"] = library.functionNames.count
    }
    guard let data = try? JSONSerialization.data(withJSONObject: info, options: [.sortedKeys]),
          data.count < Int(capacity) else { return -1 }
    data.withUnsafeBytes { raw in
        buffer.withMemoryRebound(to: UInt8.self, capacity: Int(capacity)) { out in
            out.update(from: raw.bindMemory(to: UInt8.self).baseAddress!, count: data.count)
            out[data.count] = 0
        }
    }
    return Int32(data.count)
}

/// Peak shader arithmetic in TFLOPS: `precision` 32 (float) or 16 (half),
/// a million threads of eight FMA chains, timed by the GPU.
@_cdecl("cb_gpu_fma_tflops")
public nonisolated func cb_gpu_fma_tflops(_ precision: Int32, _ ms: Int32) -> Double {
    guard ms >= 0, let device = GPUBench.device,
          let pipeline = GPUBench.pipeline(precision == 16 ? "cb_fma16" : "cb_fma32") else { return 0 }
    let threads = 1 << 20
    guard let out = device.makeBuffer(length: threads * 16, options: .storageModePrivate) else { return 0 }
    var iters: UInt32 = 2048
    let seconds = GPUBench.time(ms: ms) { buffer in
        guard let encoder = buffer.makeComputeCommandEncoder() else { return false }
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(out, offset: 0, index: 0)
        encoder.setBytes(&iters, length: 4, index: 1)
        let width = pipeline.threadExecutionWidth
        let group = MTLSize(width: min(pipeline.maxTotalThreadsPerThreadgroup, width * 8), height: 1, depth: 1)
        encoder.dispatchThreads(MTLSize(width: threads, height: 1, depth: 1), threadsPerThreadgroup: group)
        encoder.endEncoding()
        return true
    }
    guard seconds > 0 else { return 0 }
    return Double(threads) * Double(iters) * 64 / seconds * 1e-12
}

/// Device-memory bandwidth in GB/s: a copy of `megabytes` into another
/// buffer as large, counted as a read and a write of every byte.
@_cdecl("cb_gpu_bandwidth_gbs")
public nonisolated func cb_gpu_bandwidth_gbs(_ megabytes: Int32, _ ms: Int32) -> Double {
    guard ms >= 0, let device = GPUBench.device, let pipeline = GPUBench.pipeline("cb_copy") else { return 0 }
    let bytes = Int(max(megabytes, 16)) << 20
    guard let src = device.makeBuffer(length: bytes, options: .storageModePrivate),
          let dst = device.makeBuffer(length: bytes, options: .storageModePrivate) else { return 0 }
    let seconds = GPUBench.time(ms: ms) { buffer in
        guard let encoder = buffer.makeComputeCommandEncoder() else { return false }
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(src, offset: 0, index: 0)
        encoder.setBuffer(dst, offset: 0, index: 1)
        let group = MTLSize(width: min(pipeline.maxTotalThreadsPerThreadgroup, 256), height: 1, depth: 1)
        encoder.dispatchThreads(MTLSize(width: bytes / 16, height: 1, depth: 1), threadsPerThreadgroup: group)
        encoder.endEncoding()
        return true
    }
    guard seconds > 0 else { return 0 }
    return Double(bytes) * 2 / seconds * 1e-9
}

/// MPS's matrix multiply of two `n` × `n` matrices in GPU memory, in
/// GFLOPS (2n³ a multiply): `precision` 32 or 16.
@_cdecl("cb_gpu_matmul_gflops")
public nonisolated func cb_gpu_matmul_gflops(_ n: Int32, _ precision: Int32, _ ms: Int32) -> Double {
    guard ms >= 0, n > 0, let device = GPUBench.device else { return 0 }
    let size = Int(n)
    let type: MPSDataType = precision == 16 ? .float16 : .float32
    let element = precision == 16 ? 2 : 4
    let rowBytes = MPSMatrixDescriptor.rowBytes(forColumns: size, dataType: type)
    let descriptor = MPSMatrixDescriptor(rows: size, columns: size, rowBytes: rowBytes, dataType: type)
    guard rowBytes >= size * element,
          let a = device.makeBuffer(length: rowBytes * size, options: .storageModePrivate),
          let b = device.makeBuffer(length: rowBytes * size, options: .storageModePrivate),
          let c = device.makeBuffer(length: rowBytes * size, options: .storageModePrivate) else { return 0 }
    let ma = MPSMatrix(buffer: a, descriptor: descriptor)
    let mb = MPSMatrix(buffer: b, descriptor: descriptor)
    let mc = MPSMatrix(buffer: c, descriptor: descriptor)
    let multiply = MPSMatrixMultiplication(device: device, transposeLeft: false, transposeRight: false,
                                           resultRows: size, resultColumns: size, interiorColumns: size,
                                           alpha: 1, beta: 0)
    let seconds = GPUBench.time(ms: ms) { buffer in
        multiply.encode(commandBuffer: buffer, leftMatrix: ma, rightMatrix: mb, resultMatrix: mc)
        return true
    }
    guard seconds > 0 else { return 0 }
    return 2 * pow(Double(size), 3) / seconds * 1e-9
}

/// MPS's Gaussian blur (sigma 4) over a 4096 × 4096 half-float RGBA image,
/// in megapixels a second: an image-processing workload rather than a peak.
@_cdecl("cb_gpu_blur_mpix")
public nonisolated func cb_gpu_blur_mpix(_ ms: Int32) -> Double {
    guard ms >= 0, let device = GPUBench.device else { return 0 }
    let side = 4096
    let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba16Float, width: side,
                                                              height: side, mipmapped: false)
    descriptor.storageMode = .private
    descriptor.usage = [.shaderRead, .shaderWrite]
    guard let source = device.makeTexture(descriptor: descriptor),
          let destination = device.makeTexture(descriptor: descriptor) else { return 0 }
    let blur = MPSImageGaussianBlur(device: device, sigma: 4)
    let seconds = GPUBench.time(ms: ms) { buffer in
        blur.encode(commandBuffer: buffer, sourceTexture: source, destinationTexture: destination)
        return true
    }
    guard seconds > 0 else { return 0 }
    return Double(side * side) / seconds * 1e-6
}

// The C entry points in Bench/ (from CodeBench), declared by name: this
// target has no bridging header.
@_silgen_name("cb_spec_count") private nonisolated func cb_spec_count() -> Int32
@_silgen_name("cb_spec_id") private nonisolated func cb_spec_id(_ index: Int32) -> UnsafePointer<CChar>?
@_silgen_name("cb_spec_run") private nonisolated func cb_spec_run(_ id: UnsafePointer<CChar>?, _ size: Int32, _ out: UnsafeMutableRawPointer?) -> Int32
@_silgen_name("cb_cpu_clock_ghz") private nonisolated func cb_cpu_clock_ghz(_ ms: Int32) -> Double
@_silgen_name("cb_cpu_fma_gflops") private nonisolated func cb_cpu_fma_gflops(_ precision: Int32, _ ms: Int32) -> Double
@_silgen_name("cb_cpu_triad_gbs") private nonisolated func cb_cpu_triad_gbs(_ megabytes: Int32, _ ms: Int32) -> Double
@_silgen_name("cb_cpu_latency_ns") private nonisolated func cb_cpu_latency_ns(_ kilobytes: Int32, _ ms: Int32) -> Double

/// Keeps the `@_cdecl` entry points above, and the C ones `spec` and
/// cpu-z call (Bench/), in the Release binary's export table: Python finds
/// them by name through dlopen(NULL), which the linker cannot see, so
/// without a call from code it keeps they are dead-stripped. Every call
/// returns at once for these arguments.
public func _cbGPUBenchKeepAlive() -> Int {
    var sum = Int(cb_gpu_info_json(nil, 0))
    sum &+= Int(cb_gpu_fma_tflops(32, -1))
    sum &+= Int(cb_gpu_bandwidth_gbs(16, -1))
    sum &+= Int(cb_gpu_matmul_gflops(0, 32, -1))
    sum &+= Int(cb_gpu_blur_mpix(-1))
    sum &+= Int(cb_spec_count())
    sum &+= cb_spec_id(-1) == nil ? 0 : 1
    sum &+= Int(cb_spec_run(nil, 0, nil))
    sum &+= Int(cb_cpu_clock_ghz(-1))
    sum &+= Int(cb_cpu_fma_gflops(32, -1))
    sum &+= Int(cb_cpu_triad_gbs(1, -1))
    sum &+= Int(cb_cpu_latency_ns(1, -1))
    return sum
}
