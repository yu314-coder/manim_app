// VideoEncoderProbe.swift — which VideoToolbox encoder this device can
// actually use, asked at run time.
//
// `h264_videotoolbox` is not a software codec with a slow path: ffmpeg's
// wrapper only ever binds Apple's hardware encoder, so above the size that
// encoder supports `avcodec_open2` fails outright and the render falls back
// to software mpeg4 — or, before the fix, produced empty partial files.
//
// Where the ceiling sits belongs to the media engine, not the OS, and it
// moves between devices — H.264 stops at 4096x2304 on an M4 / M3 iPad Air
// but reportedly reaches 8K on an iPhone 17 Pro Max. So it is measured, not
// written down.
//
// This mirrors python-ios-lib's `manim/utils/ios_encoder.py` (which is what
// actually drives the render) in native Swift, so Settings can show a live
// answer without starting Python.
import Foundation
import VideoToolbox
import CoreMedia

enum VideoEncoderProbe {

    /// What the user asked for. `auto` follows the probe.
    enum Preference: String, CaseIterable, Identifiable {
        case auto, h264, hevc
        var id: String { rawValue }
        var label: String {
            switch self {
            case .auto: return "Auto"
            case .h264: return "H.264"
            case .hevc: return "HEVC"
            }
        }
        var detail: String {
            switch self {
            case .auto: return "Use H.264 when the device can encode it at this size, otherwise HEVC."
            case .h264: return "Widest compatibility. Not available above ~4K on most devices."
            case .hevc: return "Reaches 8K on every Apple silicon media engine measured so far. Smaller files."
            }
        }
    }

    /// Whether VideoToolbox binds a *hardware* encoder for this codec + size.
    ///
    /// Creating a session is not proof on its own — one comes back either way
    /// on macOS. The answer is in
    /// `kVTCompressionPropertyKey_UsingHardwareAcceleratedVideoEncoder`, which
    /// the session refuses to report when no hardware encoder took the job.
    static func hardwareAvailable(codec: CMVideoCodecType,
                                  width: Int, height: Int) -> Bool {
        let key = "\(codec)-\(width)x\(height)"
        if let hit = cache[key] { return hit }

        var session: VTCompressionSession?
        let created = VTCompressionSessionCreate(
            allocator: kCFAllocatorDefault,
            width: Int32(width), height: Int32(height),
            codecType: codec,
            encoderSpecification: nil,
            imageBufferAttributes: nil,
            compressedDataAllocator: nil,
            outputCallback: nil, refcon: nil,
            compressionSessionOut: &session)
        guard created == noErr, let s = session else {
            cache[key] = false
            return false
        }
        defer { VTCompressionSessionInvalidate(s) }

        // The symbol is iOS 17.4+, but the property itself is older and the
        // deployment target is 17.0 — fall back to its documented string so
        // the probe still answers on 17.0-17.3 instead of the whole feature
        // requiring a newer OS.
        let hwKey: CFString
        if #available(iOS 17.4, *) {
            hwKey = kVTCompressionPropertyKey_UsingHardwareAcceleratedVideoEncoder
        } else {
            hwKey = "UsingHardwareAcceleratedVideoEncoder" as CFString
        }

        var value: CFTypeRef?
        let status = withUnsafeMutablePointer(to: &value) { ptr -> OSStatus in
            VTSessionCopyProperty(
                s,
                key: hwKey,
                allocator: kCFAllocatorDefault,
                valueOut: UnsafeMutableRawPointer(ptr))
        }
        let ok = (status == noErr) && ((value as? Bool) ?? false)
        cache[key] = ok
        return ok
    }

    static func h264Available(width: Int, height: Int) -> Bool {
        hardwareAvailable(codec: kCMVideoCodecType_H264, width: width, height: height)
    }
    static func hevcAvailable(width: Int, height: Int) -> Bool {
        hardwareAvailable(codec: kCMVideoCodecType_HEVC, width: width, height: height)
    }

    /// What `auto` would choose at this size — the same order the render uses.
    static func autoChoice(width: Int, height: Int) -> String {
        if h264Available(width: width, height: height) { return "H.264" }
        if hevcAvailable(width: width, height: height) { return "HEVC" }
        return "mpeg4 (software)"
    }

    /// Highest ladder entry this codec still encodes in hardware, for display.
    static func ceiling(codec: CMVideoCodecType) -> String {
        for q in RenderResolution.ladder {           // 8K → 480p
            let s = RenderResolution.pixelSize(forQuality: q)
            if hardwareAvailable(codec: codec, width: s.w, height: s.h) {
                return "\(q) (\(s.w)×\(s.h))"
            }
        }
        return "not available"
    }

    /// Probing spins up a real compression session, so remember the answers.
    private static var cache: [String: Bool] = [:]
}
