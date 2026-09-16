/*
 * Scroll-driven choreography for the WebGL story, as pure data and maths (no three.js), so it can be
 * tested and tuned on its own. Time is `u`: chapters elapsed, 0..5. World units: the buyer's phone is
 * about 5.6 tall and sits near the origin facing +z.
 */

export type Vec3 = readonly [number, number, number]

export type Pose = {
  position: Vec3
  rotation: Vec3
  /** 0 hides the object. */
  scale: number
}

export type Keyframe = { at: number } & Pose

export function easeInOutCubic(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function lerpVec(a: Vec3, b: Vec3, t: number): Vec3 {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
}

/** The pose at `u`, eased between the surrounding keyframes and held before the first and after the last. */
export function samplePose(track: readonly Keyframe[], u: number): Pose {
  const first = track[0]
  if (u <= first.at) return first
  for (let i = 1; i < track.length; i++) {
    const next = track[i]
    if (u < next.at) {
      const previous = track[i - 1]
      const t = easeInOutCubic((u - previous.at) / (next.at - previous.at))
      return {
        position: lerpVec(previous.position, next.position, t),
        rotation: lerpVec(previous.rotation, next.rotation, t),
        scale: lerp(previous.scale, next.scale, t),
      }
    }
  }
  return track[track.length - 1]
}

function key(at: number, position: Vec3, rotation: Vec3 = [0, 0, 0], scale = 1): Keyframe {
  return { at, position, rotation, scale }
}

/** Where the buyer's phone screen is, for props that come out of it. */
const PHONE_OUT: Vec3 = [-1.3, 0.2, 0.3]
const PARCEL: Vec3 = [2.25, -1.5, 1.1]
const PRODUCT_TARGETS: Vec3[] = [
  [1.35, 1.8, 1.3],
  [2.35, 0.05, 2.0],
  [1.3, -1.85, 1.5],
]

export const tracks = {
  buyerPhone: [
    key(0, [0.9, 0, 0], [0.04, -0.34, 0]),
    key(0.8, [0.9, 0, 0], [0.04, -0.3, 0]),
    key(1.2, [-1.3, 0, 0], [0.02, 0.28, 0]),
    key(2.2, [-1.4, 0.05, 0], [0.02, 0.22, 0]),
    key(3.8, [-1.5, 0, 0], [0.02, 0.26, 0]),
    key(4.25, [-2.1, 0, 0.2], [0.02, 0.36, 0]),
  ],
  templateCard: [
    key(0, [0.9, 0.3, 0.3], [0, -0.3, 0], 0),
    key(0.35, [-2.15, 1.25, 1.7], [0.06, 0.42, -0.04]),
    key(0.85, [-2.1, 1.2, 1.8], [0.05, 0.38, -0.03]),
    key(1.15, [-1.2, 0.6, 0.2], [0, 0.2, 0], 0),
  ],
  products: [0, 1, 2].map((i) => {
    const target = PRODUCT_TARGETS[i]
    const start = 1.1 + i * 0.14
    const leave = 2.05 + i * 0.1
    return [
      key(start, PHONE_OUT, [0, 0.3, 0], 0),
      key(start + 0.38, target, [0.05 - i * 0.05, -0.42, 0.05 - i * 0.04]),
      key(leave, [target[0], target[1] + 0.05, target[2]], [0.03 - i * 0.04, -0.36, 0.04 - i * 0.04]),
      key(leave + 0.35, PARCEL, [0.3, -0.6, 0], 0),
    ]
  }),
  parcel: [
    key(2.0, PARCEL, [0.3, -0.7, 0], 0),
    key(2.4, [2.2, -1.35, 1.1], [0.28, -0.55, 0]),
    key(3.0, [2.2, -1.4, 1.1], [0.28, -0.6, 0]),
    key(3.35, [2.55, -2.05, 0.7], [0.26, -0.72, 0], 0.85),
    key(4.45, [2.5, -2.1, 0.8], [0.26, -0.6, 0], 0.85),
    key(4.95, [-0.6, -2.3, 2.1], [0.24, 0.2, 0], 0.8),
  ],
  paymentCard: [
    key(3.0, PHONE_OUT, [0, 0.3, 0], 0),
    key(3.35, [1.75, 1.3, 1.6], [0.04, -0.42, 0.03]),
    key(3.9, [1.8, 1.25, 1.7], [0.04, -0.38, 0.02]),
    key(4.2, [1.2, 1.6, 0.4], [0, -0.2, 0], 0),
  ],
  codChip: [
    key(3.15, PHONE_OUT, [0, 0.3, 0], 0),
    key(3.5, [2.75, -0.2, 2.25], [0, -0.5, -0.05]),
    key(3.9, [2.8, -0.25, 2.3], [0, -0.46, -0.04]),
    key(4.15, [2.0, -0.2, 1.0], [0, -0.3, 0], 0),
  ],
  sellerPhone: [
    key(3.84, [6.5, -0.2, -1.2], [0, -0.9, 0], 0),
    key(3.85, [6.5, -0.2, -1.2], [0, -0.9, 0], 0.82),
    key(4.35, [2.1, -0.1, -0.5], [0.02, -0.34, 0], 0.82),
  ],
} satisfies Record<string, readonly Keyframe[] | readonly (readonly Keyframe[])[]>

export type CameraPose = { position: Vec3; target: Vec3 }

/** Camera keyframes; `rotation` holds the look-at target so the same sampler can ease both. */
const cameraTrack: Keyframe[] = [
  key(0, [0.2, 0.4, 15], [0, 0, 0]),
  key(1.2, [0.7, 0.5, 14.6], [0.3, 0, 0]),
  key(2.3, [0.9, -0.4, 14.4], [0.4, -0.3, 0]),
  key(3.3, [0.6, 0.3, 14.6], [0.3, 0, 0]),
  key(4.3, [0, 0.1, 15.4], [0, -0.1, 0]),
]

/** Camera position and look-at target along the story. */
export function sampleCamera(u: number): CameraPose {
  const pose = samplePose(cameraTrack, u)
  return { position: pose.position, target: pose.rotation }
}
