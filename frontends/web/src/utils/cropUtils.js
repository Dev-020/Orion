export const createImage = (url) =>
    new Promise((resolve, reject) => {
      const image = new Image()
      image.addEventListener('load', () => resolve(image))
      image.addEventListener('error', (error) => reject(error))
      image.setAttribute('crossOrigin', 'anonymous') // needed to avoid cross-origin issues on CodeSandbox
      image.src = url
    })
  
  export function getRadianAngle(degreeValue) {
    return (degreeValue * Math.PI) / 180
  }
  
  /**
   * Returns the new bounding area of a rotated rectangle.
   */
  export function rotateSize(width, height, rotation) {
    const rotRad = getRadianAngle(rotation)
  
    return {
      width:
        Math.abs(Math.cos(rotRad) * width) + Math.abs(Math.sin(rotRad) * height),
      height:
        Math.abs(Math.sin(rotRad) * width) + Math.abs(Math.cos(rotRad) * height),
    }
  }
  
  /**
 * This function was adapted from the one in the Readme of https://github.com/DominicTobias/react-image-crop
 * @param {string} imageSrc - Image File url
 * @param {Object} pixelCrop - pixelCrop Object provided by react-easy-crop
 * @param {number} rotation - optional rotation parameter
 * @param {boolean} flip - optional flip parameter
 * @param {string} outputType - MIME type for output (e.g. 'image/png')
 */
export default async function getCroppedImg(
  imageSrc,
  pixelCrop,
  rotation = 0,
  flip = { horizontal: false, vertical: false },
  outputType = 'image/jpeg'
) {
  const image = await createImage(imageSrc)
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')

  if (!ctx) {
    return null
  }
  // ... (rest of rotation logic is fine) ...
  const rotRad = getRadianAngle(rotation)

  // calculate bounding box of the rotated image
  const { width: bBoxWidth, height: bBoxHeight } = rotateSize(
    image.width,
    image.height,
    rotation
  )

  // set canvas size to match the bounding box
  canvas.width = bBoxWidth
  canvas.height = bBoxHeight

  // translate canvas context to a central location to allow rotating and flipping around the center.
  ctx.translate(bBoxWidth / 2, bBoxHeight / 2)
  ctx.rotate(rotRad)
  ctx.scale(flip.horizontal ? -1 : 1, flip.vertical ? -1 : 1)
  ctx.translate(-image.width / 2, -image.height / 2)

  // draw rotated image
  ctx.drawImage(image, 0, 0)

  // croppedAreaPixels values are bounding box relative
  // extract the cropped image using these values
  const data = ctx.getImageData(
    pixelCrop.x,
    pixelCrop.y,
    pixelCrop.width,
    pixelCrop.height
  )

  // NOTE: For resizing to 512x512
  // 1. Create a temp canvas for the full crop at original resolution
  const tempCanvas = document.createElement('canvas')
  tempCanvas.width = pixelCrop.width
  tempCanvas.height = pixelCrop.height
  const tempCtx = tempCanvas.getContext('2d')
  tempCtx.putImageData(data, 0, 0)
  
  // 2. Draw that temp canvas onto the final 512x512 canvas with scaling
  const finalCanvas = document.createElement('canvas')
  finalCanvas.width = 512
  finalCanvas.height = 512
  const finalCtx = finalCanvas.getContext('2d')
  
  // Use 'medium' quality smoothing
  finalCtx.imageSmoothingEnabled = true;
  finalCtx.imageSmoothingQuality = 'high';

  finalCtx.drawImage(
      tempCanvas, 
      0, 0, pixelCrop.width, pixelCrop.height, 
      0, 0, 512, 512
  )

  // As Blob
  return new Promise((resolve, reject) => {
    finalCanvas.toBlob((file) => {
      resolve(file) // Return Blob directly
    }, outputType, 0.9) 
  })
}
