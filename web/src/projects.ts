/**
 * Projects for the customer view: human names and facts instead of file names and source codes.
 *
 * Every fact here was read from the data (W5 cycle 8, 14 Nov), not invented:
 * - Esplanades: IFC IfcProject.Name "Maleva tänav 18 korterelamu" (Estonian: apartment building), IfcPostalAddress
 *   "Maleva tänav 18, Tallinn, Harju maakond"; 7 IfcBuildingStorey (Vundament, 1.–5.korrus, Katus); 285 IfcSpace,
 *   211 IfcDoor, 297 IfcWindow; 5 plan sheets in the dataset. Licence: CC BY 4.0, (c) Esplan.
 * - Swiss floor: dataset answers for this floor (4 apartments, 36 doors, 28 windows, 341.45 m² of numbered rooms);
 *   title block "Grundriss 2. OG". Swiss Dwellings v3.0.0 (Archilyse AG), CC BY 4.0.
 * - Sports complex: title block "Xcel Sports Complex", design team addresses in Wisconsin; 24 sheets in the set.
 *   OpeningDesign, CC BY-SA 4.0.
 * - Duplex: IfcProject.LongName "Duplex Apartment", town Chicago, IL (sample address); 21 IfcSpace, 14 IfcDoor,
 *   2 floors (Level 1, Level 2). buildingSMART sample files, CC BY-ND 3.0.
 * - Apartment plan: CubiCasa5K (Finnish apartment plans), CC BY-NC-SA 4.0.
 * - HAER sheet: data/habs/LICENSE.md "Head House and Residence, North Elevation - Creque Marine Railway, Charlotte
 *   Amalie, St. Thomas, VI", HAER / Library of Congress, public domain mark.
 * Example chips: every one asked through the API on night 41188a4 and right (value + where), see board W5 cycle 8.
 */
export interface ProjectSheet {
  /** what a person calls it: "Floor 1", "3D model", "Door schedule" */
  label: string;
  path: string;
}
export interface Project {
  id: string;
  name: string;
  place: string;
  /** short facts for the card, e.g. "285 rooms" */
  facts: string[];
  /** what the project contains, in words ("5 floor plans + 3D model") */
  contents: string;
  /** the drawing opened first, then the others (the 3D model last) */
  sheets: ProjectSheet[];
  /** example questions, the way people talk (3–4) */
  chips: string[];
  /** example questions for the project's 3D model tab (whole-building questions), when it also has sheets */
  modelChips?: string[];
  /** one-line credit for the footer */
  credit: string;
  /** a small picture for the card: the file rendered by the viewer (first sheet) */
  kind: "building" | "model" | "floor" | "schedule" | "plan" | "historic";
}

// The catalogue itself is data: fixtures/projects.json (also read by fixtures/record.py, which records every chip's
// answer for the offline fallback).
import projectsJson from "../fixtures/projects.json";

const ESP = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18";

export const PROJECTS: Project[] = projectsJson as Project[];

/** The project a dataset path belongs to (its sheets, or the same building's model / plans). */
export function projectOf(path: string): Project | undefined {
  return PROJECTS.find((p) => p.sheets.some((s) => s.path === path))
    ?? (path.startsWith(ESP) ? PROJECTS[0] : undefined);
}

/** A storey/floor name as people say it: '1.korrus' → "floor 1", 'Vundament' → "basement", 'EG' → "ground floor". */
export function floorName(s: string): string {
  const t = s.trim();
  let m = t.match(/^(\d+)\.\s*korrus$/i);
  if (m) return `floor ${m[1]}`;
  m = t.match(/^level\s*(\d+)$/i);
  if (m) return `level ${m[1]}`;
  const map: Record<string, string> = { vundament: "basement", katus: "roof", eg: "ground floor", erdgeschoss: "ground floor", ug: "basement", dg: "attic" };
  return map[t.toLowerCase()] ?? t;
}
