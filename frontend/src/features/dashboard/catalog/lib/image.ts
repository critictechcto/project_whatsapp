/** Product image rules from the contract: JPEG or PNG, at most 8 MB, at least 500×500 px. */
export const IMAGE_TYPES = ['image/jpeg', 'image/png'] as const
export const IMAGE_ACCEPT = 'image/jpeg,image/png'
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024
export const MIN_IMAGE_PX = 500

export type ImageSize = { width: number; height: number }

/** Reads the natural size of an image file in the browser. */
export function readImageSize(file: File): Promise<ImageSize> {
  return new Promise((resolve, reject) => {
    if (typeof URL.createObjectURL !== 'function') {
      reject(new Error('Image previews are not supported here.'))
      return
    }
    const url = URL.createObjectURL(file)
    const image = new Image()
    const done = () => URL.revokeObjectURL?.(url)
    image.onload = () => {
      done()
      resolve({ width: image.naturalWidth, height: image.naturalHeight })
    }
    image.onerror = () => {
      done()
      reject(new Error('Unreadable image.'))
    }
    image.src = url
  })
}

/** Returns a message explaining why the file can't be used, or null when it passes every check. */
export async function validateProductImage(file: File, readSize: (file: File) => Promise<ImageSize> = readImageSize): Promise<string | null> {
  if (!(IMAGE_TYPES as readonly string[]).includes(file.type)) return 'Use a JPEG or PNG image.'
  if (file.size > MAX_IMAGE_BYTES) return 'The image is larger than 8 MB. Use a smaller file.'
  let size: ImageSize
  try {
    size = await readSize(file)
  } catch {
    return "This image couldn't be read. Try another JPEG or PNG."
  }
  if (size.width < MIN_IMAGE_PX || size.height < MIN_IMAGE_PX) {
    return `The image is ${size.width}×${size.height} px. Use one at least ${MIN_IMAGE_PX}×${MIN_IMAGE_PX} px.`
  }
  return null
}
