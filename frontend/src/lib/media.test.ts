import { describe, expect, it } from "vitest";

import { fitWithin, mediaKind, readExif } from "./media";

// JPEG 8×8 avec EXIF : prise le 14/03/2026 à 10:30, 1°40'30" S, 29°15' E.
const PHOTO =
  "/9j/4AAQSkZJRgABAQAAAQABAAD/4QC6RXhpZgAATU0AKgAAAAgAAodpAAQAAAABAAAAJoglAAQAAAABAAAATAAAAAAAAZADAAIAAAAUAAAAOAAAAAAyMDI2OjAzOjE0IDEwOjMwOjAwAAAEAAEAAgAAAAJTAAAAAAIABQAAAAMAAACCAAMAAgAAAAJFAAAAAAQABQAAAAMAAACaAAAAAAAAAAEAAAABAAAAKAAAAAEAAAAeAAAAAQAAAB0AAAABAAAADwAAAAEAAAAAAAAAAf/bAEMACAYGBwYFCAcHBwkJCAoMFA0MCwsMGRITDxQdGh8eHRocHCAkLicgIiwjHBwoNyksMDE0NDQfJzk9ODI8LjM0Mv/bAEMBCQkJDAsMGA0NGDIhHCEyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMv/AABEIAAgACAMBIgACEQEDEQH/xAAfAAABBQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMDAgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEUMoGRoQgjQrHBFVLR8CQzYnKCCQoWFxgZGiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4eLj5OXm5+jp6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEBAAAAAAAAAQIDBAUGBwgJCgv/xAC1EQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEKFiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery8/T19vf4+fr/2gAMAwEAAhEDEQA/AOKooor5o+PP/9k=";

const bytes = (base64: string) => Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)).buffer;

describe("readExif", () => {
  it("lit la date de prise de vue et la position", () => {
    expect(readExif(bytes(PHOTO))).toEqual({
      taken_at: "2026-03-14T10:30:00Z",
      latitude: -1.675,
      longitude: 29.25,
    });
  });

  it("ignore ce qui n'est pas un JPEG avec EXIF", () => {
    expect(readExif(new Uint8Array([1, 2, 3, 4]).buffer)).toEqual({});
    expect(readExif(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0, 2]).buffer)).toEqual({});
  });
});

describe("fitWithin", () => {
  it("réduit le plus grand côté sans agrandir", () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 2048, height: 1536 });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});

describe("mediaKind", () => {
  it("reconnaît photos, sons et vidéos", () => {
    expect(mediaKind("image/jpeg")).toBe("photo");
    expect(mediaKind("audio/webm;codecs=opus")).toBe("audio");
    expect(mediaKind("", "seance.MOV")).toBe("video");
    expect(mediaKind("application/pdf", "cr.pdf")).toBeNull();
  });
});
