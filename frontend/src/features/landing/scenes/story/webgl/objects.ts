import {
  BoxGeometry,
  CanvasTexture,
  Group,
  LinearMipmapLinearFilter,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PlaneGeometry,
  SRGBColorSpace,
  type Texture,
} from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { drawShadow } from './artwork'
import type { StoryTheme } from './theme'

/*
 * Procedural meshes for the story: phones, cards and the parcel. Design px map to world units at
 * 100 px per unit. Flat slabs with large corner radii use a thick RoundedBoxGeometry squashed on z,
 * because the geometry's radius cannot exceed half its depth.
 */

export const PX_PER_UNIT = 100

/** A 2D canvas drawn in design px and uploaded as a texture. */
export class CanvasPanel {
  readonly canvas = document.createElement('canvas')
  readonly texture: CanvasTexture
  private readonly ctx: CanvasRenderingContext2D

  constructor(
    readonly width: number,
    readonly height: number,
    private readonly resolution: number,
  ) {
    this.canvas.width = Math.round(width * resolution)
    this.canvas.height = Math.round(height * resolution)
    const ctx = this.canvas.getContext('2d')
    if (!ctx) throw new Error('2D canvas unavailable')
    this.ctx = ctx
    this.texture = new CanvasTexture(this.canvas)
    this.texture.colorSpace = SRGBColorSpace
    this.texture.minFilter = LinearMipmapLinearFilter
    this.texture.anisotropy = 4
  }

  draw(paint: (ctx: CanvasRenderingContext2D) => void) {
    const { ctx } = this
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    ctx.setTransform(this.resolution, 0, 0, this.resolution, 0, 0)
    paint(ctx)
    this.texture.needsUpdate = true
  }
}

/** A plane showing a panel's texture, with the transparent corners alpha-tested away. */
function panelMesh(panel: CanvasPanel, inset = 0) {
  return new Mesh(
    new PlaneGeometry(panel.width / PX_PER_UNIT - inset, panel.height / PX_PER_UNIT - inset),
    new MeshBasicMaterial({ map: panel.texture, alphaTest: 0.5, toneMapped: false }),
  )
}

/** A rounded slab `depth` thick with corner radius `radius` (world units). */
function slab(width: number, height: number, depth: number, radius: number, material: MeshStandardMaterial) {
  const built = radius * 2 + 0.02
  const mesh = new Mesh(new RoundedBoxGeometry(width, height, built, 4, radius), material)
  mesh.scale.z = depth / built
  return mesh
}

let shadowTexture: CanvasTexture | null = null

/** One blurred-rectangle texture shared by every drop shadow; disposed with the scene. */
export function getShadowTexture() {
  if (!shadowTexture) {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 128
    const ctx = canvas.getContext('2d')
    if (ctx) drawShadow(ctx, 128)
    shadowTexture = new CanvasTexture(canvas)
  }
  return shadowTexture
}

export function releaseShadowTexture() {
  shadowTexture?.dispose()
  shadowTexture = null
}

/** A soft shadow behind an object of the given size, offset down and to the right. */
function dropShadow(theme: StoryTheme, width: number, height: number, depth: number, opacity: number) {
  const mesh = new Mesh(
    new PlaneGeometry(width * 1.6, height * 1.45),
    new MeshBasicMaterial({
      map: getShadowTexture(),
      color: theme.ink,
      transparent: true,
      opacity,
      depthWrite: false,
      toneMapped: false,
    }),
  )
  mesh.position.set(width * 0.06, -height * 0.07, -depth)
  mesh.renderOrder = -1
  return mesh
}

export function createPhone(theme: StoryTheme, screen: CanvasPanel) {
  const group = new Group()
  const width = screen.width / PX_PER_UNIT + 0.12
  const height = screen.height / PX_PER_UNIT + 0.12
  const depth = 0.3

  group.add(
    slab(width, height, depth, 0.34, new MeshStandardMaterial({ color: theme.ink, roughness: 0.4, metalness: 0.2 })),
  )
  const display = panelMesh(screen)
  display.position.z = depth / 2 + 0.004
  group.add(display)
  group.add(dropShadow(theme, width, height, 0.6, 0.2))
  return group
}

export function createCard(theme: StoryTheme, face: CanvasPanel) {
  const group = new Group()
  const width = face.width / PX_PER_UNIT
  const height = face.height / PX_PER_UNIT
  const depth = 0.07

  group.add(slab(width, height, depth, 0.12, new MeshStandardMaterial({ color: theme.card, roughness: 0.85 })))
  const front = panelMesh(face, 0.01)
  front.position.z = depth / 2 + 0.003
  group.add(front)
  group.add(dropShadow(theme, width, height, 0.35, 0.16))
  return group
}

export function createParcel(label: CanvasPanel) {
  const group = new Group()
  const [width, height, depth] = [1.5, 1.04, 1.1]

  group.add(
    new Mesh(
      new RoundedBoxGeometry(width, height, depth, 3, 0.05),
      new MeshStandardMaterial({ color: '#cfae7c', roughness: 0.95 }),
    ),
  )
  const tape = new Mesh(new BoxGeometry(0.28, 0.012, depth + 0.004), new MeshStandardMaterial({ color: '#e2cba2', roughness: 0.6 }))
  tape.position.y = height / 2
  group.add(tape)

  const front = panelMesh(label)
  front.position.set(-0.1, 0.06, depth / 2 + 0.004)
  group.add(front)
  return group
}

/** Disposes every geometry, material and texture under `root`. */
export function disposeTree(root: Group) {
  const textures = new Set<Texture>()
  root.traverse((object) => {
    if (!(object instanceof Mesh)) return
    object.geometry.dispose()
    const materials = Array.isArray(object.material) ? object.material : [object.material]
    for (const material of materials) {
      if ('map' in material && material.map) textures.add(material.map as Texture)
      material.dispose()
    }
  })
  textures.forEach((texture) => texture.dispose())
  releaseShadowTexture()
}
