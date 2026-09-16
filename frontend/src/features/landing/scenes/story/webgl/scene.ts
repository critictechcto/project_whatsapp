import { DirectionalLight, Group, HemisphereLight, PerspectiveCamera, Scene, WebGLRenderer, type Object3D } from 'three'
import { clamp01 } from '../../../lib/useScrollProgress'
import { STORY_CHAPTER_COUNT } from '../storyChapters'
import {
  buyerChat,
  buyerMessages,
  messagesShown,
  sellerChat,
  sellerEarlier,
  sellerMessages,
  storyBeats,
  visibleBeats,
} from '../storyScreens'
import {
  COD_CHIP,
  PARCEL_LABEL,
  PAYMENT_CARD,
  PRODUCT_CARD,
  TEMPLATE_CARD,
  drawChatScreen,
  drawCodChip,
  drawParcelLabel,
  drawPaymentCard,
  drawProductCard,
  drawTemplateCard,
} from './artwork'
import { CanvasPanel, createCard, createParcel, createPhone, disposeTree } from './objects'
import { loadThemeFonts, readTheme } from './theme'
import { sampleCamera, samplePose, tracks, type Pose } from './timeline'

/*
 * The three.js scroll story: a buyer's phone, the props that come out of it and the seller's phone,
 * posed from scroll progress. Renders on demand only — when progress or the pointer moves, until the
 * eased values settle — and not at all while inactive (offscreen or hidden tab).
 */

export type StoryScene = {
  /** Section progress 0..1. */
  setProgress: (progress: number) => void
  /** Pointer position over the section, -1..1 on each axis (0, 0 at rest). */
  setPointer: (x: number, y: number) => void
  setActive: (active: boolean) => void
  resize: (width: number, height: number) => void
  /** Resolves after the fonts load and the first frame is drawn. */
  ready: Promise<void>
  dispose: () => void
}

const SCREEN = { width: 276, height: 552 }
const MAX_DPR = 1.75

const products = [
  { name: 'Kaju Katli 250 g', price: '₹220' },
  { name: 'Soan Papdi 250 g', price: '₹100' },
  { name: 'Motichoor Laddoo', price: '₹180' },
]

function applyPose(object: Object3D, pose: Pose) {
  object.visible = pose.scale > 0.002
  object.position.set(pose.position[0], pose.position[1], pose.position[2])
  object.rotation.set(pose.rotation[0], pose.rotation[1], pose.rotation[2])
  object.scale.setScalar(Math.max(pose.scale, 0.0001))
}

export function createStoryScene(canvas: HTMLCanvasElement, { onContextLost }: { onContextLost: () => void }): StoryScene {
  const theme = readTheme()
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_DPR))
  renderer.setClearColor(0x000000, 0)

  const scene = new Scene()
  const camera = new PerspectiveCamera(32, 1, 0.1, 100)
  scene.add(new HemisphereLight(theme.paper, theme.ink2, 2.4))
  const sun = new DirectionalLight('#ffffff', 2)
  sun.position.set(-4, 6, 10)
  scene.add(sun)

  // Textures
  const buyerScreen = new CanvasPanel(SCREEN.width, SCREEN.height, 3.5)
  const sellerScreen = new CanvasPanel(SCREEN.width, SCREEN.height, 2.5)
  const templateFace = new CanvasPanel(TEMPLATE_CARD.width, TEMPLATE_CARD.height, 3)
  const productFaces = products.map(() => new CanvasPanel(PRODUCT_CARD.width, PRODUCT_CARD.height, 3))
  const paymentFace = new CanvasPanel(PAYMENT_CARD.width, PAYMENT_CARD.height, 3)
  const codFace = new CanvasPanel(COD_CHIP.width, COD_CHIP.height, 3)
  const parcelLabel = new CanvasPanel(PARCEL_LABEL.width, PARCEL_LABEL.height, 3)

  // Objects
  const root = new Group()
  const buyerPhone = createPhone(theme, buyerScreen)
  const sellerPhone = createPhone(theme, sellerScreen)
  const templateCard = createCard(theme, templateFace)
  const productCards = productFaces.map((face) => createCard(theme, face))
  const paymentCard = createCard(theme, paymentFace)
  const codChip = createCard(theme, codFace)
  const parcel = createParcel(parcelLabel)
  root.add(sellerPhone, buyerPhone, templateCard, ...productCards, parcel, paymentCard, codChip)
  scene.add(root)

  /* ---------- Texture state: redrawn only when a chapter beat changes ---------- */

  const drawn = { buyer: -1, seller: -1, statuses: -1, paid: -1, shipped: -1 }

  const drawStatic = () => {
    productFaces.forEach((face, i) => face.draw((ctx) => drawProductCard(ctx, theme, products[i].name, products[i].price)))
    codFace.draw((ctx) => drawCodChip(ctx, theme))
  }

  const drawBeats = (u: number) => {
    const chapter = Math.min(STORY_CHAPTER_COUNT - 1, Math.max(0, Math.floor(u)))
    const beats = visibleBeats(clamp01(u - chapter), storyBeats[chapter])

    const buyer = messagesShown(buyerMessages, chapter, beats)
    if (buyer.length !== drawn.buyer) {
      drawn.buyer = buyer.length
      buyerScreen.draw((ctx) =>
        drawChatScreen(ctx, theme, { ...SCREEN, header: buyerChat, messages: buyer, business: true }),
      )
    }
    const seller = messagesShown(sellerMessages, chapter, beats)
    if (seller.length !== drawn.seller) {
      drawn.seller = seller.length
      sellerScreen.draw((ctx) =>
        drawChatScreen(ctx, theme, { ...SCREEN, header: sellerChat, messages: [sellerEarlier, ...seller], business: false }),
      )
    }
    const statuses = chapter > 0 ? 3 : beats
    if (statuses !== drawn.statuses) {
      drawn.statuses = statuses
      templateFace.draw((ctx) => drawTemplateCard(ctx, theme, statuses))
    }
    const paid = Number(chapter > 3 || (chapter === 3 && beats >= 3))
    if (paid !== drawn.paid) {
      drawn.paid = paid
      paymentFace.draw((ctx) => drawPaymentCard(ctx, theme, paid === 1))
    }
    const shipped = Number(chapter === 4 && beats >= 3)
    if (shipped !== drawn.shipped) {
      drawn.shipped = shipped
      parcelLabel.draw((ctx) => drawParcelLabel(ctx, theme, shipped === 1))
    }
  }

  /* ---------- Frame loop ---------- */

  let target = 0
  let shown = 0
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 }
  let aspect = 1
  let active = false
  let fontsReady = false
  let disposed = false
  let lost = false
  let frame = 0

  const pose = (u: number) => {
    drawBeats(u)
    applyPose(buyerPhone, samplePose(tracks.buyerPhone, u))
    applyPose(sellerPhone, samplePose(tracks.sellerPhone, u))
    applyPose(templateCard, samplePose(tracks.templateCard, u))
    productCards.forEach((card, i) => applyPose(card, samplePose(tracks.products[i], u)))
    applyPose(parcel, samplePose(tracks.parcel, u))
    applyPose(paymentCard, samplePose(tracks.paymentCard, u))
    applyPose(codChip, samplePose(tracks.codChip, u))

    // Pull the camera back on narrow stages so the props stay in frame.
    const fit = aspect < 1.15 ? Math.min(1.5, 1.15 / aspect) : 1
    const cam = sampleCamera(u)
    const [tx, ty, tz] = cam.target
    camera.position.set(
      tx + (cam.position[0] - tx) * fit + pointer.x * 0.6,
      ty + (cam.position[1] - ty) * fit - pointer.y * 0.4,
      tz + (cam.position[2] - tz) * fit,
    )
    camera.lookAt(tx, ty, tz)
  }

  const render = () => {
    frame = 0
    const delta = target - shown
    shown = Math.abs(delta) < 0.0005 ? target : shown + delta * 0.2
    pointer.x += (pointer.targetX - pointer.x) * 0.1
    pointer.y += (pointer.targetY - pointer.y) * 0.1
    const pointerSettled = Math.abs(pointer.targetX - pointer.x) < 0.002 && Math.abs(pointer.targetY - pointer.y) < 0.002
    if (pointerSettled) {
      pointer.x = pointer.targetX
      pointer.y = pointer.targetY
    }
    pose(shown)
    renderer.render(scene, camera)
    if (shown !== target || !pointerSettled) request()
  }

  function request() {
    if (!frame && active && fontsReady && !disposed && !lost) frame = requestAnimationFrame(render)
  }

  const onLost = (event: Event) => {
    event.preventDefault()
    lost = true
    cancelAnimationFrame(frame)
    frame = 0
    onContextLost()
  }
  canvas.addEventListener('webglcontextlost', onLost)

  const ready = loadThemeFonts(theme).then(() => {
    if (disposed || lost) return
    fontsReady = true
    drawStatic()
    shown = target
    pose(shown)
    renderer.render(scene, camera)
  })

  return {
    setProgress(progress) {
      target = clamp01(progress) * STORY_CHAPTER_COUNT
      request()
    },
    setPointer(x, y) {
      pointer.targetX = x
      pointer.targetY = y
      request()
    },
    setActive(next) {
      active = next
      if (active) request()
      else {
        cancelAnimationFrame(frame)
        frame = 0
      }
    },
    resize(width, height) {
      if (width < 1 || height < 1) return
      aspect = width / height
      renderer.setSize(width, height, false)
      camera.aspect = aspect
      camera.updateProjectionMatrix()
      if (fontsReady && !lost) {
        pose(shown)
        renderer.render(scene, camera)
      }
    },
    ready,
    dispose() {
      disposed = true
      cancelAnimationFrame(frame)
      canvas.removeEventListener('webglcontextlost', onLost)
      disposeTree(root)
      renderer.dispose()
      if (!lost) renderer.forceContextLoss()
    },
  }
}
