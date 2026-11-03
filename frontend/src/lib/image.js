/**
 * Shrinks a photo in the browser before upload. Phone photos are 3-8 MB (and HEIC on iPhones); the browser can decode
 * whatever the camera made, so we hand the server a ~300 KB JPEG instead.
 */
export async function downscaleImage(file, maxSide = 1600, quality = 0.85) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  if (!blob) throw new Error("Couldn't read that photo.");
  return blob;
}
