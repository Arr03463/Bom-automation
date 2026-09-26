// AutoBOM frontend — SAMPLE FIXTURE DATA ONLY.
// This file exists so the frontend components have representative data to render.
// It is NOT a backend, NOT a data layer, and must not be wired into the real app.
// Claude Code replaces every read of window.AUTOBOM_SAMPLE with real AutoBOM data
// (ActiveBomState rows, PartsBoxInventorySnapshot records, search_components() results, etc).
window.AUTOBOM_SAMPLE = {
  // Parsed from a real PartsBox export the user provided (uploads/partsbox-parts (1).csv).
  // No manufacturer/category/package column exists in that export -- left blank rather than fabricated,
  // matching the audit's note that this PartsBox account does not populate those fields.
  partsbox: [
    {
      "part_id": "pb-0",
      "mpn": "0",
      "manufacturer": "",
      "description": "Jumper Resistor",
      "category": "",
      "package": "",
      "stock": 28,
      "locations": [
        {
          "name": "A1-(0 Ohms)",
          "quantity": 28,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-1",
      "mpn": "0.15 Ohm",
      "manufacturer": "",
      "description": "0.15 Ohm Resistor",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "A1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-2",
      "mpn": "04025C102KAT4A",
      "manufacturer": "",
      "description": "0402 1nF 50 V ±10 % Tolerance X7R Surface Mount Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 90,
      "locations": [
        {
          "name": "B4",
          "quantity": 90,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "voltage": "50V",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-3",
      "mpn": "0402B222K500CT",
      "manufacturer": "",
      "description": "50V 2.2nF X7R ±10% 0402 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "B4",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "voltage": "50V",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-4",
      "mpn": "0402YD105KAT2A",
      "manufacturer": "",
      "description": "Multilayer Ceramic Capacitor, 1 F, 10%, X5R, 16 V, 0402 [1005 Metric] Rohs Compliant: Yes",
      "category": "",
      "package": "",
      "stock": 62,
      "locations": [
        {
          "name": "C1",
          "quantity": 62,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-5",
      "mpn": "06031A101KAT2A",
      "manufacturer": "",
      "description": "100V 100pF C0G 卤10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 120,
      "locations": [
        {
          "name": "B4",
          "quantity": 116,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Rx Flex Bat",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "100V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-6",
      "mpn": "06031C104KAT4A",
      "manufacturer": "",
      "description": "100V 100nF X7R 卤10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 45,
      "locations": [
        {
          "name": "C1",
          "quantity": 45,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "100V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-7",
      "mpn": "06031U470FAT2A",
      "manufacturer": "",
      "description": "100V 47pF C0G 卤1% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 104,
      "locations": [
        {
          "name": "DAB-140-70-6k-1-x1",
          "quantity": 80,
          "space_type": "Project",
          "project_name": "DAB"
        },
        {
          "name": "B3",
          "quantity": 24,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "100V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-8",
      "mpn": "06033C104KAT4A",
      "manufacturer": "",
      "description": "25V 100nF X7R 卤10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 44,
      "locations": [
        {
          "name": "C1",
          "quantity": 44,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "25V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-9",
      "mpn": "06035A180KAT2A",
      "manufacturer": "",
      "description": "0603 18 pF 50 V ±10 % Tolerance C0G/NP0 SMT Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "50V",
        "tolerance": "±10%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-10",
      "mpn": "06035C102KAT2A",
      "manufacturer": "",
      "description": "50V 1nF X7R 卤10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 83,
      "locations": [
        {
          "name": "B4",
          "quantity": 81,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Rx Flex Bat",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "50V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-11",
      "mpn": "0603N220G500CT",
      "manufacturer": "",
      "description": "50V 22pF NP0 ±2% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 17,
      "locations": [
        {
          "name": "C1",
          "quantity": 17,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "50V",
        "tolerance": "±2%",
        "dielectric": "NP0"
      }
    },
    {
      "part_id": "pb-12",
      "mpn": "0603YC104J4T4A",
      "manufacturer": "",
      "description": "Multilayer Ceramic Capacitors MLCC - SMD/SMT 16V 0.1uF X7R 0603 5% AEC-Q200",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "C1",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "16V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-13",
      "mpn": "0603ZD106KAT2A",
      "manufacturer": "",
      "description": "10V 10uF X5R 卤10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 52,
      "locations": [
        {
          "name": "C1",
          "quantity": 50,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Rx Flex Bat",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "10V",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-14",
      "mpn": "0685H9120-01",
      "manufacturer": "",
      "description": "Electric Fuse, Fast Blow, 12A, 125VAC, 32VDC, 150A (IR), Surface Mount, 1206",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "F2-19",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206"
      }
    },
    {
      "part_id": "pb-15",
      "mpn": "0685P9200-01",
      "manufacturer": "",
      "description": "Fuse Chip Fast Acting 20A 50V SMD Solder Pad 1206 3.2 X 1.58 X 0.63mm Ceramic T/",
      "category": "",
      "package": "",
      "stock": 28,
      "locations": [
        {
          "name": "F2-13",
          "quantity": 28,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "50V"
      }
    },
    {
      "part_id": "pb-16",
      "mpn": "0686F6000-01",
      "manufacturer": "",
      "description": "Electric Fuse, Fast Blow, 6A, 32VAC, 63VDC, 35A (IR), Surface Mount, 0603",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "F2-17",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603"
      }
    },
    {
      "part_id": "pb-17",
      "mpn": "08051C102K4T2A",
      "manufacturer": "",
      "description": "0805 1 nF 100 V ±10 % Tolerance X7R Surface Mount Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 48,
      "locations": [
        {
          "name": "B4",
          "quantity": 48,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "100V",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-18",
      "mpn": "08051C104KAT4A",
      "manufacturer": "",
      "description": "Cap Ceramic 0.1uF 100V X7R 10% Pad SMD 0805 125C T/R",
      "category": "",
      "package": "",
      "stock": 100,
      "locations": [
        {
          "name": "C1",
          "quantity": 100,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "100V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-19",
      "mpn": "08051C105K4T2A",
      "manufacturer": "",
      "description": "100V 1uF X7R 卤10% 0805 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 19,
      "locations": [
        {
          "name": "C1",
          "quantity": 15,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "DCD-xVB-90-012-250-4-x0_Variant-1",
          "quantity": 4,
          "space_type": "Project",
          "project_name": "DCD"
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "100V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-20",
      "mpn": "08052U330KAT2A",
      "manufacturer": "",
      "description": "Cap Ceramic 33pF 200V C0G 10% SMD 0805 125°C T/R",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "200V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-21",
      "mpn": "08052U680JAT2A",
      "manufacturer": "",
      "description": "0805 U 68PF Ceramic Multilayer Capacitor, 200V DC, +125C, C0G Dielectric, +/-5% SMD",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "200V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-22",
      "mpn": "08053A101KAT2A",
      "manufacturer": "",
      "description": "0805 100 pF 25 V ±10 % Tolerance C0G/NP0 SMT Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B4",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "25V",
        "tolerance": "±10%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-23",
      "mpn": "08053D106KAT2A",
      "manufacturer": "",
      "description": "0805 10 uF 25 V ±10 % Tolerance X5R Surface Mount Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 59,
      "locations": [
        {
          "name": "C1",
          "quantity": 59,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "25V",
        "tolerance": "±10%",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-24",
      "mpn": "08055A100JAT2A",
      "manufacturer": "",
      "description": "50V 10pF C0G 卤5% 0805 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "B3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "50V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-25",
      "mpn": "08055C333J4T2A",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 50V, 5% +Tol, 5% -Tol, X7R, 15% TC, 0.033uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 20,
      "locations": [
        {
          "name": "C1",
          "quantity": 20,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-26",
      "mpn": "08055U111FAT2A",
      "manufacturer": "",
      "description": "50V 110pF C0G 卤1% 0805 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B4",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "50V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-27",
      "mpn": "08055U180JAT2A",
      "manufacturer": "",
      "description": "U 0805 (2012Metric) Ceramic Capacitor 0.079Lx0.049W 2.01mmx1.25mm C0G NP0 ±5% 18pF",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-28",
      "mpn": "0805N100G250CT",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 25V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.00001uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-29",
      "mpn": "0805N101J631CT",
      "manufacturer": "",
      "description": "630V 100pF NP0 ±5% 0805 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B2",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "630V",
        "tolerance": "±5%",
        "dielectric": "NP0"
      }
    },
    {
      "part_id": "pb-30",
      "mpn": "0805N220J500CT",
      "manufacturer": "",
      "description": "50V 22pF NP0 ±5% 0805 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 100,
      "locations": [
        {
          "name": "C1",
          "quantity": 100,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "50V",
        "tolerance": "±5%",
        "dielectric": "NP0"
      }
    },
    {
      "part_id": "pb-31",
      "mpn": "1.5K Ohm",
      "manufacturer": "",
      "description": "1.5K Ohm Resistor",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": []
    },
    {
      "part_id": "pb-32",
      "mpn": "100k Ohm",
      "manufacturer": "",
      "description": "100K Resistor",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "A4",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-33",
      "mpn": "101X14W221MV4T",
      "manufacturer": "",
      "description": "Cap Feed Through 220pF 100VDC X7R 20% Flat 0603 125C",
      "category": "",
      "package": "",
      "stock": 228,
      "locations": [
        {
          "name": "E1-15",
          "quantity": 228,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-34",
      "mpn": "111121K00121GQTAF9LM",
      "manufacturer": "",
      "description": "1111 (2828Metric) Ceramic Capacitor 0.110Lx0.110W 2.79mmx2.79mm C0G NP0 ±2% 120pF",
      "category": "",
      "package": "",
      "stock": 15,
      "locations": [
        {
          "name": "B2",
          "quantity": 15,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "tolerance": "±2%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-35",
      "mpn": "111121K00181GQTAF9LM",
      "manufacturer": "",
      "description": "1111 (2828Metric) ceramic capacitor 0.110Lx0.110W 2.79mmx2.79mm C0G NP0 ±2% 180pF",
      "category": "",
      "package": "",
      "stock": 36,
      "locations": [
        {
          "name": "B2",
          "quantity": 36,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "tolerance": "±2%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-36",
      "mpn": "111121K00181JQT",
      "manufacturer": "",
      "description": "Cap Cer 180PF 1KV C0G/NP0 1111",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B2",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-37",
      "mpn": "111121K00221JQT",
      "manufacturer": "",
      "description": "RF Cap Cer 220PF 1KV C0G/NP0 1111",
      "category": "",
      "package": "",
      "stock": 62,
      "locations": [
        {
          "name": "B2",
          "quantity": 62,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-38",
      "mpn": "111121K00680GQTAF9LM",
      "manufacturer": "",
      "description": "RF Cap Cer 68PF 1KV C0G/NP0 1111",
      "category": "",
      "package": "",
      "stock": 35,
      "locations": [
        {
          "name": "B2",
          "quantity": 35,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-39",
      "mpn": "111122K00100GQTAF9LM",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 2000V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.00001uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-40",
      "mpn": "111122K00510GQTAF9LM",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 2000V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.000051uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-41",
      "mpn": "111122K00620GQTAF9LM",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 2000V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.000062uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 68,
      "locations": [
        {
          "name": "B2",
          "quantity": 68,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-42",
      "mpn": "111122K01P20BQTAF9LM",
      "manufacturer": "",
      "description": "Cap Ceramic 1.2pF 2000V C0G 0.1pF Pad SMD 1111 125C T/R",
      "category": "",
      "package": "",
      "stock": 35,
      "locations": [
        {
          "name": "B1",
          "quantity": 35,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "voltage": "2000V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-43",
      "mpn": "111122K01P80BQTAF9LM",
      "manufacturer": "",
      "description": "Cap Cer 1.8PF 2KV C0G/NP0 1111",
      "category": "",
      "package": "",
      "stock": 56,
      "locations": [
        {
          "name": "B1",
          "quantity": 56,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-44",
      "mpn": "111122K02P00BQTAF9LM",
      "manufacturer": "",
      "description": "Cap Ceramic 2pF 2000V C0G 0.1pF Pad SMD 1111 125C T/R",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "voltage": "2000V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-45",
      "mpn": "111122K02P70BQTAF9LM",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 2000V, 3.7037% +Tol, 3.7037% -Tol, C0G, 30ppm/Cel TC, 0.0000027uF, Surface...",
      "category": "",
      "package": "",
      "stock": 30,
      "locations": [
        {
          "name": "B1",
          "quantity": 30,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-46",
      "mpn": "111125000471GQTAF9LM",
      "manufacturer": "",
      "description": "Cap Ceramic 470pF 500V C0G 2% Pad SMD 1111 125C",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": [],
      "characteristics": {
        "package": "1111",
        "voltage": "500V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-47",
      "mpn": "111125000681GQTAF9LM",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.00068uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "B4",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-48",
      "mpn": "12061A181JAT2A",
      "manufacturer": "",
      "description": "Capacitor Ceramic 180pF 100 Volt C0G 5% Surface Mount 1206 125C Paper",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B4",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-49",
      "mpn": "12061C105KAT4A",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 100V, 10% +Tol, 10% -Tol, X7R, 15% TC, 1uF, Surface Mount, 1206",
      "category": "",
      "package": "",
      "stock": 44,
      "locations": [
        {
          "name": "C1",
          "quantity": 44,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-50",
      "mpn": "12061C225KAT4A",
      "manufacturer": "",
      "description": "100V 2.2uF X7R 卤10% 1206 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "C1",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "100V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-51",
      "mpn": "12062A302JAT2A",
      "manufacturer": "",
      "description": "3nF ±5% C0G(NP0) 200V 1206 SMD mount 3.2mm(Length)*1.6mm(width)",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B4",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "200V",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-52",
      "mpn": "12065D475MAT2A",
      "manufacturer": "",
      "description": "50V 4.7uF X5R 卤20% 1206 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "50V",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-53",
      "mpn": "12067A220JAT2A",
      "manufacturer": "",
      "description": "500V 22pF C0G 卤5% 1206 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "500V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-54",
      "mpn": "12103D226KAT2A",
      "manufacturer": "",
      "description": "25V 22uF X5R 卤10% 1210 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 179,
      "locations": [
        {
          "name": "C1",
          "quantity": 179,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1210",
        "voltage": "25V",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-55",
      "mpn": "1210B224K251CT",
      "manufacturer": "",
      "description": "1210 0.22 uF 250 V ±10 % Tolerance X7R SMT Multilayer Ceramic Capacitor",
      "category": "",
      "package": "",
      "stock": 22,
      "locations": [
        {
          "name": "C1",
          "quantity": 22,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1210",
        "voltage": "250V",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-56",
      "mpn": "1212VS-111MEB",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.117uH, 20%, 1 Element, Air-Core, SMD, 4745",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "C2",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-57",
      "mpn": "1285AS-H-R56M=P2",
      "manufacturer": "",
      "description": "Inductor Power Shielded Wirewound 0.56uH 20% 1MHz Metal 2.8A 0.059Ohm DCR 0806 T/R",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "C2",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-58",
      "mpn": "1285AS-H-R68M=P2",
      "manufacturer": "",
      "description": "Inductor Power Shielded Wirewound 0.68uH 20% 1MHz Metal 2.5A 0.072Ohm DCR 0806 T/R",
      "category": "",
      "package": "",
      "stock": 19,
      "locations": [
        {
          "name": "C2",
          "quantity": 19,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-59",
      "mpn": "132-13SMGLB",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.206uH, 2%, 1 Element, Air-Core, SMD, 4226",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "C2",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-60",
      "mpn": "1515SQ-47NGEC",
      "manufacturer": "",
      "description": "RF inductor, 47nH air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "C2",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-61",
      "mpn": "1614911-6 (CPF0805B25KE1)",
      "manufacturer": "",
      "description": "Res Thin Film 0805 25K Ohm 0.1% 1/10W ±25ppm/°C Molded SMD SMD Paper T/R",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "A4",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805"
      }
    },
    {
      "part_id": "pb-62",
      "mpn": "18122C105JAT2A",
      "manufacturer": "",
      "description": "200V 1uF X7R 卤5% 1812 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "200V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-63",
      "mpn": "1812PC474KAT1A",
      "manufacturer": "",
      "description": "250V 470nF X7R 卤10% 1812 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 20,
      "locations": [
        {
          "name": "C1",
          "quantity": 20,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "250V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-64",
      "mpn": "1909763-1",
      "manufacturer": "",
      "description": "CONN UMCC JACK STR 50OHM SMD / U.FL (UMCC) Connector Jack, Male Pin 50Ohm Surface Mount Solder",
      "category": "",
      "package": "",
      "stock": 104,
      "locations": [
        {
          "name": "Cabinet Bin-#83 RF Connectors",
          "quantity": 99,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Amplifier 1kW v1",
          "quantity": 5,
          "space_type": "Project",
          "project_name": "Amplifier 1kW"
        }
      ]
    },
    {
      "part_id": "pb-65",
      "mpn": "1K Ohm",
      "manufacturer": "",
      "description": "1K Ohm Resistor",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "A3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-66",
      "mpn": "1N5351BRLG",
      "manufacturer": "",
      "description": "ON SEMICONDUCTOR - 1N5351BRLG - Zener Single Diode, 14 V, 5 W, 017AA, 5 %, 2 Pins, 200 °C",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "D1-17",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-67",
      "mpn": "1N5819HW-7-F",
      "manufacturer": "",
      "description": "1N5819HW Series 40 V 1 A Surface Mount Schottky Barrier Rectifier - SOD-123",
      "category": "",
      "package": "",
      "stock": 16,
      "locations": [
        {
          "name": "C4 - 7",
          "quantity": 16,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "40V"
      }
    },
    {
      "part_id": "pb-68",
      "mpn": "1SMA5930BT3G",
      "manufacturer": "",
      "description": "Zener Diode Single 16V 5% 10Ohm 1500mW Automotive 2-Pin SMA T/R / DIODE ZENER 16V 1.5W SMA",
      "category": "",
      "package": "",
      "stock": 13,
      "locations": [
        {
          "name": "D1-19",
          "quantity": 13,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "16V"
      }
    },
    {
      "part_id": "pb-69",
      "mpn": "1SMB5946B-13",
      "manufacturer": "",
      "description": "Zener Diode, 75V V(Z), 5%, 0.55W, Silicon, Unidirectional",
      "category": "",
      "package": "",
      "stock": 11,
      "locations": [
        {
          "name": "D3-11",
          "quantity": 11,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "75V"
      }
    },
    {
      "part_id": "pb-70",
      "mpn": "2014VS-111MED",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.108uH, 20%, 1 Element, Air-Core, SMD, 7754",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C2",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-71",
      "mpn": "2014VS-151MEB",
      "manufacturer": "",
      "description": "Power inductor, 155nH high current, 20% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": []
    },
    {
      "part_id": "pb-72",
      "mpn": "2014VS-151MED",
      "manufacturer": "",
      "description": "Power inductor, 155nH high current, 20% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 21,
      "locations": [
        {
          "name": "C2",
          "quantity": 21,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-73",
      "mpn": "2014VS-201MEB",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.202uH, 20%, 1 Element, Air-Core, SMD, 7754",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C2",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-74",
      "mpn": "2014VS-251MED",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.257uH, 20%, 1 Element, Air-Core, SMD, 7754",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "C2",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-75",
      "mpn": "2014VS-33NMED",
      "manufacturer": "",
      "description": "General Purpose Inductor, 0.033uH, 20%, 1 Element, Air-Core, SMD, 7754",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "C2",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-76",
      "mpn": "201S42E271KV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 200V, 10% +Tol, 10% -Tol, C0G, 30ppm/Cel TC, 0.00027uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 25,
      "locations": [
        {
          "name": "B4",
          "quantity": 25,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-77",
      "mpn": "22-23-2031",
      "manufacturer": "",
      "description": "Connector Wire to Board Header 3 Position 2.54mm Solder Straight Thru-Hole (Color may vary)",
      "category": "",
      "package": "",
      "stock": 104,
      "locations": [
        {
          "name": "Cabinet Bin-#90",
          "quantity": 104,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-78",
      "mpn": "22201C106MAT2A",
      "manufacturer": "",
      "description": "100V 10uF X7R 卤20% 2220 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS",
      "category": "",
      "package": "",
      "stock": 50,
      "locations": [
        {
          "name": "DCD-xVB-90-012-250-4-x0_Variant-1",
          "quantity": 40,
          "space_type": "Project",
          "project_name": "DCD"
        },
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "2220",
        "voltage": "100V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-79",
      "mpn": "2222SQ-111GEB",
      "manufacturer": "",
      "description": "Inductor RF Unshielded Wirewound 0.11uH 2% 50MHz 140Q-Factor Air 5.7A 0.0065Ohm DCR T/R",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "C2",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-80",
      "mpn": "2222SQ-161GEB",
      "manufacturer": "",
      "description": "RF inductor, air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C2",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-81",
      "mpn": "2222SQ-301GEB",
      "manufacturer": "",
      "description": "RF inductor, air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": []
    },
    {
      "part_id": "pb-82",
      "mpn": "222523K63P00BQTAF9LM",
      "manufacturer": "",
      "description": "Cap Ceramic 3pF 3600V C0G 0.1pF Pad SMD 2225 125C T/R",
      "category": "",
      "package": "",
      "stock": 22,
      "locations": [
        {
          "name": "B1",
          "quantity": 22,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "3600V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-83",
      "mpn": "251R14S240JV4T",
      "manufacturer": "",
      "description": "Cap Ceramic 24pF 250V C0G 5% Pad SMD 0603 125C Ultra Low ESR T/R",
      "category": "",
      "package": "",
      "stock": 20,
      "locations": [
        {
          "name": "B3",
          "quantity": 20,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-84",
      "mpn": "251R15S100GV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 10pF 250V C0G 2% Pad SMD 0805 125C T/R",
      "category": "",
      "package": "",
      "stock": 26,
      "locations": [
        {
          "name": "B3",
          "quantity": 26,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-85",
      "mpn": "251R15S101FV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 100pF 250V C0G 1% Pad SMD 0805 125C T/R",
      "category": "",
      "package": "",
      "stock": 11,
      "locations": [
        {
          "name": "B4",
          "quantity": 11,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-86",
      "mpn": "251R15S120GV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.000012uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "B3",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-87",
      "mpn": "251R15S151JV4E",
      "manufacturer": "",
      "description": "S 0805 (2012Metric) Ceramic Capacitor 0.080Lx0.050W 2.03mmx1.27mm C0G NP0 ±5% 150pF",
      "category": "",
      "package": "",
      "stock": 11,
      "locations": [
        {
          "name": "B4",
          "quantity": 11,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-88",
      "mpn": "251R15S1R3CV4E",
      "manufacturer": "",
      "description": "S 0805 (2012Metric) Ceramic Capacitor 0.080Lx0.050W 2.03mmx1.27mm C0G NP0 ±0.25pF 1.3pF",
      "category": "",
      "package": "",
      "stock": 19,
      "locations": [
        {
          "name": "B3",
          "quantity": 19,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-89",
      "mpn": "251R15S200GV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.00002uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "B3",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-90",
      "mpn": "251R15S270GV4E",
      "manufacturer": "",
      "description": "S 0805 (2012Metric) Ceramic Capacitor 0.080Lx0.050W 2.03mmx1.27mm C0G NP0 ±2% 27pF",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "B3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±2%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-91",
      "mpn": "251R15S390JV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 39pF 250V C0G 5% Pad SMD 0805 125C Ultra Low ESR T/R",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "B3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-92",
      "mpn": "251R15S470JV4E",
      "manufacturer": "",
      "description": "Capacitor, Ceramic, 47pF, 250VDC, 5-% Tol, 5+% Tol, NP0-TC Code, -30, 30ppm-TC RoHS Compliant: Yes",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B3",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "dielectric": "NP0"
      }
    },
    {
      "part_id": "pb-93",
      "mpn": "251R15S510GV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.000051uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-94",
      "mpn": "251R15S560JV4E",
      "manufacturer": "",
      "description": "S 0805 (2012Metric) Ceramic Capacitor 0.080Lx0.050W 2.03mmx1.27mm C0G NP0 卤5% 56pF",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "B3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-95",
      "mpn": "251R15S5R6CV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 5.6pF 250V C0G 0.25pF Pad SMD 0805 125C T/R",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "B3 - [5.6pF 6.8pF",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-96",
      "mpn": "251R15S680JV4E",
      "manufacturer": "",
      "description": "S 0805 (2012Metric) Ceramic Capacitor 0.080Lx0.050W 2.03mmx1.27mm C0G NP0 ±5% 68pF",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "B3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-97",
      "mpn": "251R15S8R2CV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 8.2pF 250V C0G 0.25pF Pad SMD 0805 125C Ultra Low ESR T/R",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B3",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-98",
      "mpn": "251R15S910GV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 2% +Tol, 2% -Tol, C0G, 30ppm/Cel TC, 0.000091uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B2",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-99",
      "mpn": "251nH 24.4A (c251D)",
      "manufacturer": "",
      "description": "inductor c251D",
      "category": "",
      "package": "",
      "stock": 26,
      "locations": [
        {
          "name": "C3",
          "quantity": 26,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-100",
      "mpn": "28C0236-0BW-10",
      "manufacturer": "",
      "description": "Ferrite Beads Axial Choke Bead 835Ohm 100MHz 5A",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "F2-12",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-101",
      "mpn": "2929SQ-331GEC",
      "manufacturer": "",
      "description": "RF inductor, 330nH, air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 11,
      "locations": [
        {
          "name": "C2",
          "quantity": 11,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-102",
      "mpn": "2929SQ-361GEC",
      "manufacturer": "",
      "description": "RF inductor, 360nH, air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 11,
      "locations": [
        {
          "name": "C2",
          "quantity": 11,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-103",
      "mpn": "2929SQ-431GEC",
      "manufacturer": "",
      "description": "RF inductor, 430nH, air core, 2% tol, SMT, RoHS, halogen-free",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": []
    },
    {
      "part_id": "pb-104",
      "mpn": "2929SQ-501GEC",
      "manufacturer": "",
      "description": "Inductor RF Unshielded Wirewound 0.5uH 2% 50MHz 180Q-Factor Air 4.3A 0.0165Ohm DCR T/R",
      "category": "",
      "package": "",
      "stock": 19,
      "locations": [
        {
          "name": "C2",
          "quantity": 19,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-105",
      "mpn": "2N7002H-7",
      "manufacturer": "",
      "description": "Transistor Mosfet N-ch 60V 0.2A 3-PIN SOT-23 T/r",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "D4-15",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "60V"
      }
    },
    {
      "part_id": "pb-106",
      "mpn": "2N7002NXBKR",
      "manufacturer": "",
      "description": "Transistor Mosfet N-ch 60V 0.33A 3-PIN SOT-23 T/r",
      "category": "",
      "package": "",
      "stock": 96,
      "locations": [
        {
          "name": "E2-7",
          "quantity": 96,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "60V"
      }
    },
    {
      "part_id": "pb-107",
      "mpn": "352110KFT",
      "manufacturer": "",
      "description": "Res Thick Film 2512 10K Ohm 1% 2W ±100ppm/°C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "A3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-108",
      "mpn": "35212K0FT",
      "manufacturer": "",
      "description": "Res Thick Film 2512 2K Ohm 1% 2W ±100ppm/C Pad SMD Automotive T/R",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "A3",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-109",
      "mpn": "35213K0FT",
      "manufacturer": "",
      "description": "Res Thick Film 2512 3K Ohm 1% 2W ±100ppm/C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "A3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-110",
      "mpn": "3521470RFT",
      "manufacturer": "",
      "description": "Res Thick Film 2512 470 Ohm 1% 2W ±100ppm/C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "A3",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-111",
      "mpn": "3521510RFT (4-2176070-2)",
      "manufacturer": "",
      "description": "Res Thick Film 2512 510 Ohm 1% 2W ±100ppm/°C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "A3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-112",
      "mpn": "3521820RFT",
      "manufacturer": "",
      "description": "3521 Series 2512 820 Ohm 2 W ±1 % ±100 ppm/°C Surface Mount Thick Film Resistor",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "A3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-113",
      "mpn": "3522750RFT (4-2176231-6)",
      "manufacturer": "",
      "description": "Fixed Resistor, Thick Film, 3W, 750ohm, 250V, 1% +/-Tol, 100ppm/Cel, Surface Mount, 2512",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "A3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-114",
      "mpn": "3522910RFT",
      "manufacturer": "",
      "description": "Res Thick Film 2512 910 Ohm 1% 3W ±100ppm/C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 15,
      "locations": [
        {
          "name": "A3",
          "quantity": 15,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-115",
      "mpn": "3550100RFT",
      "manufacturer": "",
      "description": "Fixed Resistor, Metal Glaze/thick Film, 5W, 100ohm, 300V, 1% +/-Tol, 100ppm/Cel, Surface Mount, 4320",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "A2",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-116",
      "mpn": "356036RFT (3-2176406-8)",
      "manufacturer": "",
      "description": "Chip Resistor 36Ω ±1% 6W ±100ppm/°C 4527 SMD 11.6mm × 6.85mm × 1.2mm",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": [],
      "characteristics": {
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-117",
      "mpn": "380uH 3.3A (750811041)",
      "manufacturer": "",
      "description": "TRANS FLYBACK",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "C3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-118",
      "mpn": "3SMAJ5930B-TP",
      "manufacturer": "",
      "description": "Zener Diode, 16V V(Z), 5%, 3W, Silicon, Unidirectional, DO-214AC",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "D1-20",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "16V"
      }
    },
    {
      "part_id": "pb-119",
      "mpn": "4.99k Ohm",
      "manufacturer": "",
      "description": "4.99k Ohm Resistor",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "A4",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-120",
      "mpn": "400SGV10M12.5X13.5",
      "manufacturer": "",
      "description": "Al Electrolytic Cap 10μF 400V ±20% 5000h@105°C 135mA@120Hz 202.5mA@10kHz SMD 13mm × 13mm × 14mm",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "400V",
        "tolerance": "±20%"
      }
    },
    {
      "part_id": "pb-121",
      "mpn": "501S42E100JV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 10pF 500V C0G 5% Pad SMD 1111 125C T/R",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "B1",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "voltage": "500V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-122",
      "mpn": "501S42E101JV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 5% +Tol, 5% -Tol, C0G, 30ppm/Cel TC, 0.0001uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": [],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-123",
      "mpn": "501S42E1R0BV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 10% +Tol, 10% -Tol, C0G, 30ppm/Cel TC, 0.000001uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-124",
      "mpn": "501S42E470JV4E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 5% +Tol, 5% -Tol, C0G, 30ppm/Cel TC, 0.000047uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "B1",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-125",
      "mpn": "501S42E560JV4E",
      "manufacturer": "",
      "description": "Cap Ceramic 56pF 500V C0G 5% Pad SMD 1111 125C T/R",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "B1",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "voltage": "500V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-126",
      "mpn": "501S42E561JV3E",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 5% +Tol, 5% -Tol, C0G, 30ppm/Cel TC, 0.00056uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "B2",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-127",
      "mpn": "50SVPF10M",
      "manufacturer": "",
      "description": "Cap Aluminum Polymer 10uF 50VDC 20%( 6.3 X 5.9mm) SMD 0.04 Ohm 2500mA 5000h 105C T/R",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C1",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-128",
      "mpn": "5701-RC",
      "manufacturer": "",
      "description": "1KHz 11A 10μH 8mΩ ±15% vertical mounting，Through hole mounting 11.1mm(width)*11.1mm(height)",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C3",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "tolerance": "±15%"
      }
    },
    {
      "part_id": "pb-129",
      "mpn": "600F0R2AT250XT",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 25% +Tol, 25% -Tol, C0G, 30ppm/Cel TC, 0.0000002uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "B3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-130",
      "mpn": "600F120GT250XT",
      "manufacturer": "",
      "description": "Cap Ceramic 12pF 250V C0G 2% Pad SMD 0805 125°C Ultra Low ESR T/R",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "B3",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-131",
      "mpn": "600F181FT250XT",
      "manufacturer": "",
      "description": "0805 (2012METRIC) Ceramic Capacitor Atc 600F 250V 180PF ±1% C0G NP0",
      "category": "",
      "package": "",
      "stock": 25,
      "locations": [
        {
          "name": "B4",
          "quantity": 25,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "tolerance": "±1%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-132",
      "mpn": "600F200GT250XT",
      "manufacturer": "",
      "description": "20pF 250V 0805 Ceramic Multilayer Capacitor (P90 & NP0)",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "NP0"
      }
    },
    {
      "part_id": "pb-133",
      "mpn": "600F330FT250XT",
      "manufacturer": "",
      "description": "0805 (2012METRIC) Ceramic Capacitor Atc 600F 250V 33PF ±1% C0G NP0",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "B3",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "tolerance": "±1%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-134",
      "mpn": "600F5R6BW250XT",
      "manufacturer": "",
      "description": "Cap Ceramic 5.6pF 250V C0G 0.1pF Pad SMD 0805 125°C Ultra Low ESR",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3 - [5.6pF 6.8pF",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-135",
      "mpn": "600F620FT250XT",
      "manufacturer": "",
      "description": "Cap Ceramic 62pF 250V C0G 1% Pad SMD 0805 125C Ultra Low ESR T/R",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "B3",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-136",
      "mpn": "600F750JT250XT",
      "manufacturer": "",
      "description": "0805 (2012METRIC) Ceramic Capacitor Atc 600F 250V 75PF ±5% C0G NP0",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "250V",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-137",
      "mpn": "600S510FT250XT",
      "manufacturer": "",
      "description": "0603 (1608METRIC) Ceramic Capacitor Atc 600S 250V 51PF ±1% C0G NP0",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "B3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "250V",
        "tolerance": "±1%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-138",
      "mpn": "700B272KTN50XT",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 50V, 10% +Tol, 10% -Tol, C0G, 30ppm/Cel TC, 0.0027uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "B4",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-139",
      "mpn": "73100-0154",
      "manufacturer": "",
      "description": "RF BNC Connector, 1 Contact(s), Female, Board Mount, Solder Terminal, Receptacle",
      "category": "",
      "package": "",
      "stock": 19,
      "locations": [
        {
          "name": "Cabinet Bin-#83 RF Connectors",
          "quantity": 19,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-140",
      "mpn": "742792609",
      "manufacturer": "",
      "description": "Ferrite Beads Multi-Layer 30Ohm 25% 100MHz 3A 0.04Ohm DCR 0603 T/R",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "F2-7",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603"
      }
    },
    {
      "part_id": "pb-141",
      "mpn": "742792641",
      "manufacturer": "",
      "description": "Ferrite Bead, SMT, Emi Suppressed, 300 Ohm, 2000MA, 0603, We-cbf Series",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "F2-15",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603"
      }
    },
    {
      "part_id": "pb-142",
      "mpn": "74279273",
      "manufacturer": "",
      "description": "WE-CBF Ferrite Bead 0402 20Ohm 300mA",
      "category": "",
      "package": "",
      "stock": 34,
      "locations": [
        {
          "name": "F2-11",
          "quantity": 34,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402"
      }
    },
    {
      "part_id": "pb-143",
      "mpn": "742792731",
      "manufacturer": "",
      "description": "FERRITE BEAD, 0.09OHM, 1.2A, 0402; Available until stocks are exhausted",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "F2-6",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402"
      }
    },
    {
      "part_id": "pb-144",
      "mpn": "7443091100",
      "manufacturer": "",
      "description": "Power Choke Shielded Wirewound 1uH 20% 100KHz Ferrite 34A 0.00042Ohm DCR T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 15,
      "locations": [
        {
          "name": "C2",
          "quantity": 15,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-145",
      "mpn": "744311100",
      "manufacturer": "",
      "description": "WE-HCI SMD Flat Wire High Current Inductor | FIXED IND 1UH 15A 4.6 MOHM SMD",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C2",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-146",
      "mpn": "744314101",
      "manufacturer": "",
      "description": "General Purpose Inductor, 10uH, 20%, 1 Element, Ferrite-Core, SMD, 2827",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "C3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-147",
      "mpn": "7443341000",
      "manufacturer": "",
      "description": "WE-HCC SMT High Current Inductor (Ferrite)",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-148",
      "mpn": "74435588200",
      "manufacturer": "",
      "description": "FIXED IND 82UH 7A 30.4 MOHM SMD / WE-HCI SMD Flat Wire High Current Inductor",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C3",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-149",
      "mpn": "7443643300",
      "manufacturer": "",
      "description": "ROHS3Compliant Wirewound Active Tray Wirewound Inductor -40C~125C 7MHz 2.4mOhm 33muH",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "C3",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-150",
      "mpn": "74437356010",
      "manufacturer": "",
      "description": "100KHz 44MHz 25.5A 12.5A 1μH 8.35mΩ ±20% 8030 standard mounting，SMD mount 9.2mm*6.2mm*3mm",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C2",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "tolerance": "±20%"
      }
    },
    {
      "part_id": "pb-151",
      "mpn": "74437529203470",
      "manufacturer": "",
      "description": "Power Choke Shielded Wirewound 47uH 20% 100KHz Ferrite 18.7A 0.0088Ohm DCR Tray Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "ARMSTRONG",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "C3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-152",
      "mpn": "74438336010",
      "manufacturer": "",
      "description": "FIXED IND 1UH 4A 32 MOHM SMD / 1 µH Shielded Molded Inductor 4 A 32mOhm Max 1212 (3030 Metric)",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "C2",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1212"
      }
    },
    {
      "part_id": "pb-153",
      "mpn": "7447054",
      "manufacturer": "",
      "description": "10KHz 2A 10μH 20mΩ ±20% Plugins vertical mounting，Through hole mounting 10.5mm*5.5mm*7.8mm",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C3",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "tolerance": "±20%"
      }
    },
    {
      "part_id": "pb-154",
      "mpn": "744710610",
      "manufacturer": "",
      "description": "Inductor, Rod Core, We-Sd Series, 6Uh; |Würth Elektronik 744710610",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "C3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-155",
      "mpn": "7447709151",
      "manufacturer": "",
      "description": "Power Choke Shielded Wirewound 150uH 20% 1KHz Ferrite 2.1A 0.2Ohm DCR Automotive T/R",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "C2",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-156",
      "mpn": "7447709271",
      "manufacturer": "",
      "description": "Power Choke Shielded Wirewound 270uH 20% 1KHz Ferrite 1.6A 0.33Ohm DCR Automotive T/R",
      "category": "",
      "package": "",
      "stock": 14,
      "locations": [
        {
          "name": "C3",
          "quantity": 14,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-157",
      "mpn": "7447709680",
      "manufacturer": "",
      "description": "Power Choke Shielded Wirewound 68uH 20% 1KHz Ferrite 3.2A 0.089Ohm DCR Automotive T/R",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "C3",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-158",
      "mpn": "7447714680",
      "manufacturer": "",
      "description": "Inductor Power Shielded Wirewound 68uH 20% 100KHz Ferrite 1.9A 0.132Ohm DCR Automotive AEC-Q200 T/R",
      "category": "",
      "package": "",
      "stock": 4,
      "locations": [
        {
          "name": "C3",
          "quantity": 4,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-159",
      "mpn": "7447779001",
      "manufacturer": "",
      "description": "FIXED IND 1UH 5.3A 11 MOHM SMD / WE-PD SMD Shielded Power Inductor",
      "category": "",
      "package": "",
      "stock": 18,
      "locations": [
        {
          "name": "C2",
          "quantity": 18,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-160",
      "mpn": "74479262147",
      "manufacturer": "",
      "description": "Inductor, 470Nh, 1.5A, 20%, Shielded; |Würth Elektronik 74479262147",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "C2",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-161",
      "mpn": "74479276210",
      "manufacturer": "",
      "description": "Inductor, 1Uh, 2A, 20%, Shielded; |Würth Elektronik 74479276210",
      "category": "",
      "package": "",
      "stock": 20,
      "locations": [
        {
          "name": "C2",
          "quantity": 20,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-162",
      "mpn": "74479974133",
      "manufacturer": "",
      "description": "Fixed Ind 330NH 2A 69 Mohm SMD",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C2",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-163",
      "mpn": "74HC595D,118",
      "manufacturer": "",
      "description": "Shift Register, 74HC595, Serial to Parallel, Serial to Serial, 1 Element, 8 -Bit, 16 Pins, SOIC",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "D4-16",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-164",
      "mpn": "74HC595D-Q100,118",
      "manufacturer": "",
      "description": "74HC Series 6 V 8-Bit Serial-In Serial or Parallel-Out Shift Register - SOIC-16",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "D4-16",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "6V"
      }
    },
    {
      "part_id": "pb-165",
      "mpn": "750311771",
      "manufacturer": "",
      "description": "WE-FB Flyback transformer for DC/DC Converter",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "C2",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-166",
      "mpn": "750343004",
      "manufacturer": "",
      "description": "160μH 160mΩ Through hole mounting 30.5mm(Length)*33mm(height)",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "C2",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-167",
      "mpn": "7uH - 6.5A",
      "manufacturer": "",
      "description": "Inductor",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "C3",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-168",
      "mpn": "800B470FT500XT",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 500V, 1% +Tol, 1% -Tol, C0G, 30ppm/Cel TC, 0.000047uF, Surface Mount, 1111",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "B1",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1111",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-169",
      "mpn": "875075955001",
      "manufacturer": "",
      "description": "Polymer Cap, 10Uf, 20%, 100V, Smd; |Würth Elektronik 875075955001",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-170",
      "mpn": "885012007061",
      "manufacturer": "",
      "description": "470pF ±5% C0G(NP0) 50V 0805 SMD mount 2mm(Length)*1.25mm(width)",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B4",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "50V",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-171",
      "mpn": "885012107018",
      "manufacturer": "",
      "description": "4.7μF ±20% 25V Ceramic Capacitor X5R 0805 (2012 Metric)",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "C1",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "25V",
        "tolerance": "±20%",
        "dielectric": "X5R"
      }
    },
    {
      "part_id": "pb-172",
      "mpn": "885012207060",
      "manufacturer": "",
      "description": "Ceramic Capacitor 1nF, 25VDC, 0805, ±10 %",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "B4",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±10%"
      }
    },
    {
      "part_id": "pb-173",
      "mpn": "885012207066",
      "manufacturer": "",
      "description": "WCAP-CSGP 0805 (2012Metric) Ceramic Capacitor 0.079Lx0.049W 2.00mmx1.25mm X7R ±10% 10000pF",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "C1",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-174",
      "mpn": "885012207076",
      "manufacturer": "",
      "description": "Cap Ceramic 0.47uF 25V X7R 10% Pad SMD 0805 125C T/R",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "25V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-175",
      "mpn": "885012207078",
      "manufacturer": "",
      "description": "Multilayer Ceramic Capacitor, Wcap-Csgp Series, 1UF, 10%, X7R, 25 V, 0805 [2012 Metric] Rohs Compliant: Yes",
      "category": "",
      "package": "",
      "stock": 24,
      "locations": [
        {
          "name": "C1",
          "quantity": 24,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-176",
      "mpn": "885012207110",
      "manufacturer": "",
      "description": "100pF ±10% X7R 100V 0805 SMD mount 2mm(Length)*1.25mm(width)",
      "category": "",
      "package": "",
      "stock": 220,
      "locations": [
        {
          "name": "B4",
          "quantity": 216,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "DCD-xVB-90-012-250-4-x0_Variant-1",
          "quantity": 4,
          "space_type": "Project",
          "project_name": "DCD"
        }
      ],
      "characteristics": {
        "package": "0805",
        "voltage": "100V",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-177",
      "mpn": "885342006003",
      "manufacturer": "",
      "description": "100pF ±5% C0G(NP0) 250V 0603 SMD mount 1.6mm(Length)*800μm(width)",
      "category": "",
      "package": "",
      "stock": 8,
      "locations": [
        {
          "name": "B4",
          "quantity": 8,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "250V",
        "tolerance": "±5%",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-178",
      "mpn": "885382207010",
      "manufacturer": "",
      "description": "WCAP-CSST 0805 (2012Metric) ceramic capacitor 0.079Lx0.049W 2.00mmx1.25mm X7R ±10% 270pF",
      "category": "",
      "package": "",
      "stock": 0,
      "locations": [],
      "characteristics": {
        "package": "0805",
        "tolerance": "±10%",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-179",
      "mpn": "9-2176092-2",
      "manufacturer": "",
      "description": "Res Thin Film 0805 7.32K Ohm 0.1% 0.25W(1/4W) ±25ppm/C Pad SMD T/R Medical",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "A3",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805"
      }
    },
    {
      "part_id": "pb-180",
      "mpn": "A767KN336M1JLAE042",
      "manufacturer": "",
      "description": "Aluminum Electrolytic Capacitor, Polarized, Aluminum (solid Polymer), 63V, 20% +Tol, 20% -Tol, 33uF, Surface Mount,...",
      "category": "",
      "package": "",
      "stock": 1,
      "locations": [
        {
          "name": "C1",
          "quantity": 1,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-181",
      "mpn": "A767KS106M2ALAE045",
      "manufacturer": "",
      "description": "Cap Aluminum Polymer 10uF 100VDC 20% (8 X 12mm) SMD 0.045 Ohm 1700mA 2000h 105C T/R",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "C1",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-182",
      "mpn": "A768KS397M1ELAE019",
      "manufacturer": "",
      "description": "Cap Aluminum Polymer 390uF 25V 20% Solder Cylindrical 19m Ohm 2325mA 2000 hr 125°C T/R",
      "category": "",
      "package": "",
      "stock": 18,
      "locations": [
        {
          "name": "C1",
          "quantity": 18,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "25V"
      }
    },
    {
      "part_id": "pb-183",
      "mpn": "A768MS227M1GLAV022",
      "manufacturer": "",
      "description": "Cap Aluminum Polymer 220uF 40V 20% Solder Cylindrical 22m Ohm 2200mA 2000 hr 125°C T/R",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "B4",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "40V"
      }
    },
    {
      "part_id": "pb-184",
      "mpn": "A768MS567M1ELAE017",
      "manufacturer": "",
      "description": "560uF 25V Aluminum - Polymer Capacitors Radial, Can- SMD 17mOhm 2000 Hrs 125oC",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "C1",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "25V"
      }
    },
    {
      "part_id": "pb-185",
      "mpn": "AA1210JR-073R9L",
      "manufacturer": "",
      "description": "Fixed Resistor, Metal Glaze/thick Film, 0.5W, 3.9ohm, 200V, 5% +/-Tol, 200ppm/Cel, Surface Mount, 1210",
      "category": "",
      "package": "",
      "stock": 16,
      "locations": [
        {
          "name": "A1",
          "quantity": 16,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1210"
      }
    },
    {
      "part_id": "pb-186",
      "mpn": "AC0402FR-07332KL",
      "manufacturer": "",
      "description": "62.5mW Thick Film Resistors 50V ±100ppm/℃ ±1% 332kΩ 0402 Chip Resistor - Surface Mount ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "A4",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "voltage": "50V",
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-187",
      "mpn": "AC0402KRX7R9BB562",
      "manufacturer": "",
      "description": "Multilayer Ceramic Capacitors 0.0056uF 50V X7R 10% Pad SMD 0402 125C Automotive",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "B4",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "voltage": "50V",
        "dielectric": "X7R"
      }
    },
    {
      "part_id": "pb-188",
      "mpn": "AC0603FR-0714RL",
      "manufacturer": "",
      "description": "100mW Thick Film Resistors 75V ±100ppm/℃ ±1% 14Ω 0603 Chip Resistor - Surface Mount ROHS",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "A2",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0603",
        "voltage": "75V",
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-189",
      "mpn": "AC0603FR-0715KL",
      "manufacturer": "",
      "description": "Res Thick Film 0603 15K Ohm 1% 0.1W(1/10W) ±100ppm/C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 193,
      "locations": [
        {
          "name": "A4",
          "quantity": 191,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Amplifier 1kW v1",
          "quantity": 2,
          "space_type": "Project",
          "project_name": "Amplifier 1kW"
        }
      ],
      "characteristics": {
        "package": "0603"
      }
    },
    {
      "part_id": "pb-190",
      "mpn": "AC0805FR-07100RL",
      "manufacturer": "",
      "description": "Res Thick Film 0805 100 Ohm 1% 0.125W(1/8W) ±100ppm/C Pad SMD T/R Automotive AEC-Q200",
      "category": "",
      "package": "",
      "stock": 149,
      "locations": [
        {
          "name": "A2",
          "quantity": 149,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805"
      }
    },
    {
      "part_id": "pb-191",
      "mpn": "AC0805JRNPOYBN470",
      "manufacturer": "",
      "description": "Ceramic Capacitor, Multilayer, Ceramic, 250V, 5% +Tol, 5% -Tol, C0G, 30ppm/Cel TC, 4.7e-05uF, Surface Mount, 0805",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "B3",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-192",
      "mpn": "AC1206FR-07590KL",
      "manufacturer": "",
      "description": "250mW Thick Film Resistors 200V ±100ppm/℃ ±1% 590kΩ 1206 Chip Resistor - Surface Mount ROHS",
      "category": "",
      "package": "",
      "stock": 24,
      "locations": [
        {
          "name": "A4",
          "quantity": 24,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "1206",
        "voltage": "200V",
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-193",
      "mpn": "AC1206JR-070RL",
      "manufacturer": "",
      "description": "Jumper Resistor",
      "category": "",
      "package": "",
      "stock": 139,
      "locations": [
        {
          "name": "A1-(0 Ohms)",
          "quantity": 114,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Amplifier 20W V2_Rev0 / Amplifier 20W V3_Rev0",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "SEPIC_120W_100V/12V_DCDC_V2_Variant-1",
          "quantity": 11,
          "space_type": "Project",
          "project_name": "SEPIC_120W_100V"
        },
        {
          "name": "CTR-xTP-ICL-BE-012-1-x0_Variant2",
          "quantity": 2,
          "space_type": "Project",
          "project_name": "CTR"
        }
      ]
    },
    {
      "part_id": "pb-194",
      "mpn": "ACT4060ASH-T",
      "manufacturer": "",
      "description": "Switching Regulator, Current-mode, 450kHz Switching Freq-Max, PDSO8",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "E4-6",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-195",
      "mpn": "AD5247BKSZ10-RL7",
      "manufacturer": "",
      "description": "ALSO OPERATES AT 5V SUPPLY AD5247 Gold I2C digital potentiometer 1.2MHz 5.5V 10kOhm 1mm",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "E1-20",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "5V"
      }
    },
    {
      "part_id": "pb-196",
      "mpn": "AD5247BKSZ50-RL7",
      "manufacturer": "",
      "description": "Digital Potentiometer 50kOhm 128POS Volatile Automotive 6-Pin SC-70 T/R",
      "category": "",
      "package": "",
      "stock": 40,
      "locations": [
        {
          "name": "E2-9",
          "quantity": 40,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-197",
      "mpn": "AF0402FR-07100KL",
      "manufacturer": "",
      "description": "62.5mW Thick Film Resistors 50V ±100ppm/℃ ±1% 100kΩ 0402 Chip Resistor - Surface Mount ROHS",
      "category": "",
      "package": "",
      "stock": 39,
      "locations": [
        {
          "name": "A4",
          "quantity": 39,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0402",
        "voltage": "50V",
        "tolerance": "±1%"
      }
    },
    {
      "part_id": "pb-198",
      "mpn": "AIML-0805HC-2R2M-T",
      "manufacturer": "",
      "description": "General Purpose Inductor, 2.2uH, 20%, 1 Element, Ferrite-Core, SMD, 0805",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "C2",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805"
      }
    },
    {
      "part_id": "pb-199",
      "mpn": "AIML-0805HC-4R7M-T",
      "manufacturer": "",
      "description": "Inductor Power Shielded Multi-Layer 4.7uH 20% 1MHz Ferrite 1A 0.25Ohm DCR 0805 T/R",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "package": "0805"
      }
    },
    {
      "part_id": "pb-200",
      "mpn": "AOD3N50",
      "manufacturer": "",
      "description": "Trans MOSFET N-CH 500V 2.8A 3-Pin(2+Tab) DPAK / MOSFET N-CH 500V 2.8A TO252",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "E2-6",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "500V"
      }
    },
    {
      "part_id": "pb-201",
      "mpn": "AOD600A60",
      "manufacturer": "",
      "description": "600V N-Channel MOSFET, TO-252-3, RoHS",
      "category": "",
      "package": "",
      "stock": 23,
      "locations": [
        {
          "name": "E3-2",
          "quantity": 23,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "600V"
      }
    },
    {
      "part_id": "pb-202",
      "mpn": "AP2204K-3.0TRG1",
      "manufacturer": "",
      "description": "Voltage Regulator; linear, LDO; fixed; Vout: 3V; Vin: 2.6-24V; -40+125 deg.C; SMD; SOT23-5",
      "category": "",
      "package": "",
      "stock": 24,
      "locations": [
        {
          "name": "E1-6",
          "quantity": 24,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-203",
      "mpn": "AP2205-33Y-13",
      "manufacturer": "",
      "description": "Fixed LDO Voltage Regulator, 2.3V to 24V in, 360mV Drop, 3.3V out, 200mA out, SOT-89-3",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "F1-12",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "2.3V"
      }
    },
    {
      "part_id": "pb-204",
      "mpn": "AP2205-W5-7",
      "manufacturer": "",
      "description": "250mA Adjustable 1.24V~22V positive 24V SOT-25 Linear Voltage Regulators (LDO) ROHS",
      "category": "",
      "package": "",
      "stock": 132,
      "locations": [
        {
          "name": "F1-9",
          "quantity": 128,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Amplifier 20W V2_Rev0 / Amplifier 20W V3_Rev0",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        },
        {
          "name": "Amplifier 1kW v1",
          "quantity": 2,
          "space_type": "Project",
          "project_name": "Amplifier 1kW"
        }
      ],
      "characteristics": {
        "voltage": "22V"
      }
    },
    {
      "part_id": "pb-205",
      "mpn": "AP22652W6-7",
      "manufacturer": "",
      "description": "3 V 300mA 1 Output Positive Fixed Linear Voltage Regulator IC - SOT-23-3",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "F1-7",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "3V"
      }
    },
    {
      "part_id": "pb-206",
      "mpn": "AP22653AW6-7",
      "manufacturer": "",
      "description": "Switch, precision adjustable, current limited power switch, SOT26 | Diodes Inc AP22653AW6-7",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "E1-22",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-207",
      "mpn": "AP22653W6-7",
      "manufacturer": "",
      "description": "USB Power High Side Switch Single 3V to 5.5V 2.1A 6-Pin SOT-26 T/R",
      "category": "",
      "package": "",
      "stock": 7,
      "locations": [
        {
          "name": "E1-22",
          "quantity": 7,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "3V"
      }
    },
    {
      "part_id": "pb-208",
      "mpn": "AP3128S-13",
      "manufacturer": "",
      "description": "10V~50V Flyback 23KHz~105KHz Yes Over temperature，Overvoltage，overload 700V SOIC-8 SMD mount，glue mount",
      "category": "",
      "package": "",
      "stock": 9,
      "locations": [
        {
          "name": "E4-11",
          "quantity": 9,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "50V"
      }
    },
    {
      "part_id": "pb-209",
      "mpn": "AQ13EA102JA1WE",
      "manufacturer": "",
      "description": "Cap Ceramic 0.001uF 150V C0G 5% SMD 125°C Waffle Pack",
      "category": "",
      "package": "",
      "stock": 22,
      "locations": [
        {
          "name": "B4",
          "quantity": 22,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "150V",
        "dielectric": "C0G"
      }
    },
    {
      "part_id": "pb-210",
      "mpn": "AR3PD-M3/86A",
      "manufacturer": "",
      "description": "Rectifier Diode, Avalanche, 1 Phase, 1 Element, 1.8A, 200V V(RRM), Silicon, TO-277A",
      "category": "",
      "package": "",
      "stock": 6,
      "locations": [
        {
          "name": "D2-24",
          "quantity": 6,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "200V"
      }
    },
    {
      "part_id": "pb-211",
      "mpn": "ASPI-6045S-100M-T",
      "manufacturer": "",
      "description": "Inductor Power Shielded Wirewound 10uH 20% 100KHz 2.45A 0.048Ohm DCR 2424 T/R",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "C3",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-212",
      "mpn": "ASPI-6045S-300M-T",
      "manufacturer": "",
      "description": "Inductor Power Shielded Wirewound 30uH 20% 100KHz 1.5A 0.132Ohm DCR 2424 T/R",
      "category": "",
      "package": "",
      "stock": 15,
      "locations": [
        {
          "name": "C3",
          "quantity": 15,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-213",
      "mpn": "AT42QT1010-TSHR",
      "manufacturer": "",
      "description": "Capacitive Touch Screen 1 Key 6-Pin SOT-23 T/R / IC TOUCH SENSOR 1KEY SOT23-6",
      "category": "",
      "package": "",
      "stock": 10,
      "locations": [
        {
          "name": "D4-22",
          "quantity": 10,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-214",
      "mpn": "ATTINY1614-SSNR",
      "manufacturer": "",
      "description": "8-Bit AVR Microcontroller 16Kbyte Flash 2Kbyte SRAM 14-Pin SOIC T/R - Tape and Reel",
      "category": "",
      "package": "",
      "stock": 5,
      "locations": [
        {
          "name": "E2-20",
          "quantity": 5,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-215",
      "mpn": "ATTINY412-SSFR",
      "manufacturer": "",
      "description": "IC MCU 8BIT 4KB FLASH 8SOIC / AVR series Microcontroller IC 8-Bit 16MHz 4KB (4K x 8) FLASH 8-SOIC",
      "category": "",
      "package": "",
      "stock": 13,
      "locations": [
        {
          "name": "E2-20",
          "quantity": 13,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-216",
      "mpn": "AZDC105-1AH-24DT",
      "manufacturer": "",
      "description": "AZDC105 DC High Current Power Relay 150A 60VDC switching 24VDC coil UL/CUR",
      "category": "",
      "package": "",
      "stock": 2,
      "locations": [
        {
          "name": "F1-22",
          "quantity": 2,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-217",
      "mpn": "B82559B0203A016",
      "manufacturer": "",
      "description": "Power Inductor, 20Uh, Shielded, 12.4A Rohs Compliant: Yes |EPCOS (TDK) B82559B0203A016",
      "category": "",
      "package": "",
      "stock": 3,
      "locations": [
        {
          "name": "C3",
          "quantity": 3,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-218",
      "mpn": "BAS21-TP",
      "manufacturer": "",
      "description": "Diode, Signal, Rectifier, Fast, Vr 200V, If 200MA, Pkg SOT-23, Vf 1.25V, Trr 50NS",
      "category": "",
      "package": "",
      "stock": 12,
      "locations": [
        {
          "name": "D3-10",
          "quantity": 12,
          "space_type": "Development",
          "project_name": null
        }
      ]
    },
    {
      "part_id": "pb-219",
      "mpn": "BAT54C RFG",
      "manufacturer": "",
      "description": "Rectifier Diode Small Signal Schottky 30V 0.2A 5ns 3-Pin SOT-23 T/R",
      "category": "",
      "package": "",
      "stock": 13,
      "locations": [
        {
          "name": "C4 - 2",
          "quantity": 13,
          "space_type": "Development",
          "project_name": null
        }
      ],
      "characteristics": {
        "voltage": "30V"
      }
    }
  ],

  suppliers: [
    { source: 'Mouser', mpn: 'RC0603FR-0710KL', manufacturer: 'Yageo', description: 'Thick Film Resistors 10K 1% 0603', stock: '52,314', unit_price: '$0.0021', supplier_part_number: '603-RC0603FR-0710KL' },
    { source: 'Mouser', mpn: 'RC0603JR-0710KL', manufacturer: 'Yageo', description: 'Thick Film Resistors 10K 5% 0603', stock: '103,229', unit_price: '$0.0018', supplier_part_number: '603-RC0603JR-0710KL' },
    { source: 'DigiKey', mpn: 'RC0603FR-0710KL', manufacturer: 'Yageo', description: 'RES 10K OHM 1% 1/10W 0603', stock: '87,456', unit_price: '$0.0019', supplier_part_number: '311-10.0KCRCT-ND' },
    { source: 'Mouser', mpn: 'CRCW060310K0FKEA', manufacturer: 'Vishay', description: 'Thick Film Resistors 1/10W 10K 1%', stock: '24,801', unit_price: '$0.0032', supplier_part_number: 'CRCW060310K0FKEA' },
    { source: 'DigiKey', mpn: 'RK73H1JTTD1002F', manufacturer: 'KOA Speer', description: 'RES 10K OHM 1% 1/10W 0603', stock: '32,118', unit_price: '$0.0044', supplier_part_number: '2019-RK73H1ETTP1002FCT-ND' }
  ],
  workingParts: [
    { row_id: 'r1', mpn: 'RC0603FR-0710KL', manufacturer: 'Yageo', description: 'RES 10K 1% 1/10W 0603', designators: 'R1, R4, R9', required_qty: 30, source: 'PartsBox', result_status: 'Ready', customer_reference: 'PRJ-ALD-DAB' },
    { row_id: 'r2', mpn: 'GRM188R71H104KA93D', manufacturer: 'Murata', description: 'CAP CER 0.1UF 50V X7R 0603', designators: 'C1–C8', required_qty: 80, source: 'Mouser', result_status: 'Ready', customer_reference: 'PRJ-ALD-DAB' },
    { row_id: 'r3', mpn: '', manufacturer: '', description: 'CAP CER 10UF 25V X7R 1206', designators: 'C12, C14', required_qty: 20, source: 'None', result_status: 'Needs Review', customer_reference: 'PRJ-ALD-DAB', review_reason: 'Missing MPN' },
    { row_id: 'r4', mpn: 'LT1763CS8-3.3#PBF', manufacturer: 'Analog Devices', description: 'IC REG LDO 3.3V 500MA 8SO', designators: 'U4', required_qty: 10, source: 'None', result_status: 'Needs Review', customer_reference: 'PRJ-ALD-DAB', review_reason: 'Manufacturer mismatch' },
    { row_id: 'r5', mpn: 'BSS138LT1G', manufacturer: 'onsemi', description: 'MOSFET N-CH 50V 200MA SOT23', designators: 'Q1, Q2', required_qty: 20, source: 'Mouser', result_status: 'Ready', customer_reference: 'PRJ-ALD-DAB' }
  ],
  replacementCandidates: {
    suppliers: [
      { source: 'Mouser', mpn: 'GRM31CR71E106KA12L', manufacturer: 'Murata', stock: '48,210', unit_price: '$0.1840' },
      { source: 'DigiKey', mpn: 'CL31B106KAHNNNE', manufacturer: 'Samsung', stock: '120,334', unit_price: '$0.0950' }
    ],
    partsbox: [
      { source: 'PartsBox', mpn: 'CL31B106KBHNNNE', manufacturer: 'Samsung', stock: '46', unit_price: '—' }
    ]
  },
  // Real PartsBox account here has no manufacturer field -- empty facet, not fabricated (matches the audit).
  manufacturerFacet: [],
  spaceFacet: [["Development",218],["Project",9]],
  locationFacet: [["C1",30],["B3",28],["C2",27],["B4",22],["C3",18],["B1",12],["A3",10],["B2",9],["A4",7],["Rx Flex Bat",3],["A2",3],["A1-(0 Ohms)",2],["A1",2],["Cabinet Bin-#83 RF Connectors",2],["B3 - [5.6pF 6.8pF",2],["D4-16",2],["Amplifier 20W V2_Rev0 / Amplifier 20W V3_Rev0",2],["E1-22",2],["E2-20",2],["F2-19",1],["F2-13",1],["F2-17",1],["E1-15",1],["D1-17",1],["C4 - 7",1],["D1-19",1],["D3-11",1],["Cabinet Bin-#90",1],["F2-12",1],["D4-15",1]],
  projectFacet: [["DCD",3],["Amplifier 1kW",3],["DAB",1],["SEPIC_120W_100V",1],["CTR",1]],
  registry: {
    projects: { ALD: 'NASA P2 CON (Aldrin)', SPAR: 'ARMY P2 (Sparta)', TBCA: 'TBCA POC3' },
    pcb_codes: { DAB: 'Dual Active Bridge', BUZZ: 'Bus Bar', MISC: 'Miscellaneous' }
  }
};
