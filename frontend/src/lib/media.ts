/**
 * Préparation des preuves sur le téléphone : lecture de la date et de la position des photos
 * (EXIF), compression avant envoi, reconnaissance des enregistrements audio et vidéo.
 */

export interface PhoneMeta {
  taken_at?: string;
  latitude?: number;
  longitude?: number;
}

// Au-delà, une photo est réduite avant d'être mise en file d'envoi.
export const MAX_PHOTO_SIDE = 2048;
export const MIN_BYTES_TO_COMPRESS = 600 * 1024;
const JPEG_QUALITY = 0.8;

export type MediaKind = "photo" | "audio" | "video" | null;

export function mediaKind(type: string, filename = ""): MediaKind {
  if (type.startsWith("image/")) return "photo";
  if (type.startsWith("audio/")) return "audio";
  if (type.startsWith("video/")) return "video";
  const suffix = filename.toLowerCase().split(".").pop() ?? "";
  if (["mp3", "m4a", "aac", "ogg", "opus", "wav", "amr"].includes(suffix)) return "audio";
  if (["mp4", "mov", "webm", "3gp"].includes(suffix)) return "video";
  return null;
}

/** Date de prise de vue et position GPS lues dans l'EXIF d'un JPEG (rien si absentes). */
export function readExif(buffer: ArrayBuffer): PhoneMeta {
  const view = new DataView(buffer);
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return {};
  let offset = 2;
  while (offset + 4 <= view.byteLength) {
    const marker = view.getUint16(offset);
    if (marker === 0xffda) break; // début de l'image : plus de métadonnées
    const size = view.getUint16(offset + 2);
    if (marker === 0xffe1 && view.getUint32(offset + 4) === 0x45786966) {
      try {
        return readTiff(view, offset + 10);
      } catch {
        return {};
      }
    }
    offset += 2 + size;
  }
  return {};
}

function readTiff(view: DataView, tiff: number): PhoneMeta {
  const little = view.getUint16(tiff) === 0x4949;
  const u16 = (at: number) => view.getUint16(at, little);
  const u32 = (at: number) => view.getUint32(at, little);
  const entries = (ifd: number) => {
    const tags = new Map<number, number>();
    const count = u16(ifd);
    for (let i = 0; i < count; i += 1) tags.set(u16(ifd + 2 + i * 12), ifd + 2 + i * 12);
    return tags;
  };
  const ascii = (entry: number) => {
    const count = u32(entry + 4);
    const start = count <= 4 ? entry + 8 : tiff + u32(entry + 8);
    let text = "";
    for (let i = 0; i < count; i += 1) {
      const code = view.getUint8(start + i);
      if (!code) break;
      text += String.fromCharCode(code);
    }
    return text;
  };
  const degrees = (entry: number) => {
    const start = tiff + u32(entry + 8);
    const [d, m, s] = [0, 1, 2].map((i) => u32(start + i * 8) / (u32(start + i * 8 + 4) || 1));
    return d + m / 60 + s / 3600;
  };

  const meta: PhoneMeta = {};
  const root = entries(tiff + u32(tiff + 4));
  const exifPointer = root.get(0x8769);
  if (exifPointer !== undefined) {
    const original = entries(tiff + u32(exifPointer + 8)).get(0x9003);
    const match =
      original !== undefined && /^(\d{4}):(\d\d):(\d\d) (\d\d:\d\d:\d\d)/.exec(ascii(original));
    if (match) meta.taken_at = `${match[1]}-${match[2]}-${match[3]}T${match[4]}Z`;
  }
  const gpsPointer = root.get(0x8825);
  if (gpsPointer !== undefined) {
    const gps = entries(tiff + u32(gpsPointer + 8));
    const [latRef, lat, lonRef, lon] = [1, 2, 3, 4].map((tag) => gps.get(tag));
    if (lat !== undefined && lon !== undefined) {
      const round = (value: number) => Math.round(value * 1e6) / 1e6;
      meta.latitude = round(
        degrees(lat) * (latRef !== undefined && ascii(latRef) === "S" ? -1 : 1),
      );
      meta.longitude = round(
        degrees(lon) * (lonRef !== undefined && ascii(lonRef) === "W" ? -1 : 1),
      );
    }
  }
  return meta;
}

/** Dimensions réduites en gardant les proportions. */
export function fitWithin(width: number, height: number, max = MAX_PHOTO_SIDE) {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/**
 * Photo prête à mettre en file d'envoi : réduite et recompressée en JPEG si elle est lourde,
 * avec la date et la position lues avant compression (le JPEG produit n'a plus d'EXIF).
 */
export async function preparePhoto(
  file: File,
): Promise<{ blob: Blob; filename: string; meta: PhoneMeta }> {
  const meta = file.type === "image/jpeg" ? readExif(await file.arrayBuffer()) : {};
  if (file.size < MIN_BYTES_TO_COMPRESS || typeof createImageBitmap !== "function")
    return { blob: file, filename: file.name, meta };
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const { width, height } = fitWithin(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob || blob.size >= file.size) return { blob: file, filename: file.name, meta };
    const filename = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return { blob, filename, meta };
  } catch {
    // Format que le navigateur ne sait pas décoder (HEIC…) : envoyé tel quel.
    return { blob: file, filename: file.name, meta };
  }
}
