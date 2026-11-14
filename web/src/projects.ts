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
  /** one-line credit for the footer */
  credit: string;
  /** a small picture for the card: the file rendered by the viewer (first sheet) */
  kind: "building" | "model" | "floor" | "schedule" | "plan" | "historic";
}

const ESP = "data/ifc_models/bsc-esplanades_1807-ep-ar-v18";

export const PROJECTS: Project[] = [
  {
    id: "esplanades",
    name: "Maleva 18 apartment building",
    place: "Tallinn, Estonia",
    facts: ["5 floors + basement", "285 rooms", "211 doors"],
    contents: "5 floor plans + 3D model",
    sheets: [
      ...[1, 2, 3, 4, 5].map((n) => ({ label: `Floor ${n}`, path: `${ESP}_plan-0${n}-${n}-korrus.pdf` })),
      { label: "3D model", path: `${ESP}.ifc` },
    ],
    chips: [
      "How many doors are on this floor?",
      "Which is the biggest room on this floor?",
      "Do the plan and the 3D model agree on the windows on this floor?",
      "How many windows in the whole building?",
    ],
    credit: "Drawings and model: Esplan (esplan.ee), CC BY 4.0",
    kind: "building",
  },
  {
    id: "swiss",
    name: "Apartment floor",
    place: "Switzerland",
    facts: ["4 apartments", "36 doors", "341 m² of rooms"],
    contents: "1 floor plan (2nd floor)",
    sheets: [{ label: "2nd floor", path: "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf" }],
    chips: [
      "How many doors on this floor?",
      "How big is apartment B?",
      "How many apartments are on this floor?",
      "Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?",
    ],
    credit: "Drawing: Swiss Dwellings v3.0.0 (Archilyse AG), rendered by us, CC BY 4.0",
    kind: "floor",
  },
  {
    id: "duplex",
    name: "Duplex apartment",
    place: "Sample building, US",
    facts: ["2 floors", "21 rooms", "14 doors"],
    contents: "3D model",
    sheets: [{ label: "3D model", path: "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc" }],
    chips: [
      "How many doors are in this model?",
      "How many rooms are on each floor?",
      "Which storey has the most doors?",
      "How tall is the building?",
    ],
    credit: "Model: buildingSMART Duplex Apartment sample, CC BY-ND 3.0",
    kind: "model",
  },
  {
    id: "sports",
    name: "Xcel Sports Complex",
    place: "Wisconsin, US",
    facts: ["24 drawing sheets", "door & finish schedules"],
    contents: "door schedule sheet",
    sheets: [{ label: "Door schedule (A-801)", path: "data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf" }],
    chips: [
      "How many doors are in the door schedule?",
    ],
    credit: "Drawings: OpeningDesign and the project team in the title block, CC BY-SA 4.0",
    kind: "schedule",
  },
  {
    id: "flat",
    name: "Apartment floor plan",
    place: "Finland",
    facts: ["scanned plan", "Finnish room codes"],
    contents: "1 plan image",
    sheets: [{ label: "Plan", path: "data/cubicasa5k/colorful-4539.png" }],
    chips: [
      "How many bedrooms are there?",
      "Is there a sauna?",
      "Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?",
    ],
    credit: "Plan: CubiCasa5K, CC BY-NC-SA 4.0",
    kind: "plan",
  },
  {
    id: "habs",
    name: "Creque Marine Railway, head house",
    place: "Charlotte Amalie, St. Thomas (US Virgin Islands)",
    facts: ["historic measured drawing", "scanned sheet"],
    contents: "1 scanned sheet",
    sheets: [{ label: "North elevation", path: "data/habs/vi0026_sheet_00003.jpg" }],
    chips: [
      "What kind of drawing is this?",
      "What is the scale of this drawing?",
      "When was this drawing made?",
    ],
    credit: "Drawing: HAER, National Park Service; Library of Congress, public domain",
    kind: "historic",
  },
];

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
