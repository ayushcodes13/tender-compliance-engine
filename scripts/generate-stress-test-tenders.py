import os
import fitz  # PyMuPDF

os.makedirs("stress-test-fixtures", exist_ok=True)

def create_pdf_with_drawings(filename, build_fn):
    doc = fitz.open()
    build_fn(doc)
    filepath = os.path.join("stress-test-fixtures", filename)
    doc.save(filepath)
    doc.close()
    print(f"Generated: {filepath}")

# -------------------------------------------------------------
# 1. Normal Standard Tender
# -------------------------------------------------------------
def build_normal_tender(doc):
    page = doc.new_page(width=595, height=842) # A4
    page.insert_text((50, 50), "GOVERNMENT PROCUREMENT DIVISION", fontsize=14, fontname="hebo")
    page.insert_text((50, 70), "Tender No: NIT/2026/EE/104 - Technical Specifications", fontsize=11, fontname="helv")
    page.insert_text((50, 90), "Item: High Precision Digital Multimeter & Oscilloscope Calibration Workstation", fontsize=10, fontname="hebo")
    
    # Table header
    y = 130
    page.draw_rect(fitz.Rect(50, y - 15, 545, y + 15), color=(0.2, 0.4, 0.6), fill=(0.9, 0.93, 0.97))
    page.insert_text((55, y), "Sl. No.", fontsize=9, fontname="hebo")
    page.insert_text((100, y), "Parameter / Feature", fontsize=9, fontname="hebo")
    page.insert_text((260, y), "Required Technical Specification", fontsize=9, fontname="hebo")
    page.insert_text((430, y), "Compliance (Yes/No)", fontsize=9, fontname="hebo")
    page.insert_text((500, y), "Remarks", fontsize=9, fontname="hebo")
    
    specs = [
        ("1", "DC Voltage Range", "0 to 1000 V with minimum 6.5 digit resolution", "", ""),
        ("2", "Basic DCV Accuracy", "± 0.0035% of reading + 0.0005% of range or better", "", ""),
        ("3", "AC Voltage Bandwidth", "3 Hz to 300 kHz true RMS measurement", "", ""),
        ("4", "Resistance Range", "100 mΩ to 100 MΩ (2-wire and 4-wire configuration)", "", ""),
        ("5", "Current Measurement", "10 µA to 10 A continuous DC and AC capability", "", ""),
        ("6", "Sampling Rate", "Up to 50,000 readings/second into internal buffer", "", ""),
        ("7", "Connectivity Interfaces", "USB 3.0, GPIB (IEEE-488), and LXI Gigabit Ethernet", "", ""),
        ("8", "Display", "4.3 inch high-resolution TFT color graphical display", "", ""),
        ("9", "Operating Temperature", "0 °C to +50 °C at up to 80% relative humidity", "", ""),
        ("10", "Input Power Supply", "100 V - 240 V AC, 50/60 Hz universal power source", "", ""),
        ("11", "Calibration Certificate", "NIST / NABL traceable calibration certificate included", "", ""),
        ("12", "Warranty", "36 months comprehensive onsite warranty", "", ""),
    ]
    
    y = 160
    for sl, param, spec, comp, rem in specs:
        page.draw_line((50, y + 15), (545, y + 15), color=(0.8, 0.8, 0.8), width=0.5)
        page.insert_text((55, y + 8), sl, fontsize=9, fontname="helv")
        page.insert_text((100, y + 8), param, fontsize=9, fontname="helv")
        page.insert_text((260, y + 8), spec, fontsize=8.5, fontname="helv")
        y += 28

create_pdf_with_drawings("01_normal_standard_tender.pdf", build_normal_tender)

# -------------------------------------------------------------
# 2. Multi-Column Grid Tender (Wide Schema)
# -------------------------------------------------------------
def build_multi_column_tender(doc):
    page = doc.new_page(width=842, height=595) # A4 Landscape
    page.insert_text((50, 40), "SECTION VII — DETAILED TECHNICAL SPECIFICATIONS GRID", fontsize=13, fontname="hebo")
    page.insert_text((50, 58), "Industrial Continuous Laser Welder System · Bid Specification Sheet", fontsize=9.5, fontname="helv")
    
    y = 85
    page.draw_rect(fitz.Rect(40, y - 15, 800, y + 15), color=(0.1, 0.2, 0.4), fill=(0.85, 0.88, 0.95))
    headers = [
        (45, "Sl. No."),
        (85, "Assembly / Module"),
        (200, "Technical Parameter"),
        (330, "Specified Requirement / Range"),
        (510, "Unit"),
        (560, "Standard"),
        (650, "Compliance (Yes/No)"),
        (740, "Remarks"),
    ]
    for x, h in headers:
        page.insert_text((x, y), h, fontsize=8.5, fontname="hebo")
        
    rows = [
        ("1.0", "Laser Generator", "Average Laser Power Output", "≥ 3000 continuous fiber laser source", "Watts", "ISO 11553", "", ""),
        ("2.0", "Laser Generator", "Central Laser Wavelength", "1070 ± 10 nm fiber output", "nm", "IEC 60825-1", "", ""),
        ("3.0", "Laser Generator", "Beam Quality (BPP)", "≤ 2.0 mm·mrad single-mode output", "mm·mrad", "ISO 11146", "", ""),
        ("4.0", "Process Head", "Collimating Focal Length", "100 mm fused silica optics with air knife", "mm", "DIN EN 60825", "", ""),
        ("5.0", "Process Head", "Focusing Lens Length", "250 mm focal length with integrated camera", "mm", "Factory Spec", "", ""),
        ("6.0", "CNC Gantry", "X-Axis Work Envelope", "1500 mm linear travel with ball screw drive", "mm", "ISO 230-2", "", ""),
        ("7.0", "CNC Gantry", "Y-Axis Work Envelope", "1000 mm linear travel with AC servomotors", "mm", "ISO 230-2", "", ""),
        ("8.0", "CNC Gantry", "Z-Axis Work Envelope", "500 mm linear travel with fail-safe brake", "mm", "ISO 230-2", "", ""),
        ("9.0", "CNC Gantry", "Positioning Accuracy", "± 0.02 mm across full volumetric travel", "mm", "VDI/DGQ 3441", "", ""),
        ("10.0", "Cooling Unit", "Water Chiller Capacity", "Dual-circuit refrigeration capacity ≥ 12 kW", "kW", "CE Mark", "", ""),
        ("11.0", "Safety Enclosure", "Laser Protective Housing", "Class 1 laser safety room enclosure with interlocks", "Class", "EN 12254", "", ""),
    ]
    
    y = 110
    for r in rows:
        page.draw_line((40, y + 14), (800, y + 14), color=(0.8, 0.8, 0.8), width=0.5)
        page.insert_text((45, y + 6), r[0], fontsize=8, fontname="helv")
        page.insert_text((85, y + 6), r[1], fontsize=8, fontname="hebo")
        page.insert_text((200, y + 6), r[2], fontsize=8, fontname="helv")
        page.insert_text((330, y + 6), r[3], fontsize=7.5, fontname="helv")
        page.insert_text((510, y + 6), r[4], fontsize=8, fontname="helv")
        page.insert_text((560, y + 6), r[5], fontsize=8, fontname="helv")
        y += 26

create_pdf_with_drawings("02_multi_column_grid_tender.pdf", build_multi_column_tender)

# -------------------------------------------------------------
# 3. Deep Hierarchical Tender (Multi-level Units & Subsystems)
# -------------------------------------------------------------
def build_deep_hierarchy_tender(doc):
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 45), "NATIONAL RESEARCH INSTITUTE FOR ADVANCED PHYSICS", fontsize=12, fontname="hebo")
    page1.insert_text((50, 65), "ANNEXURE I: TECHNICAL SPECIFICATIONS AND COMPLIANCE MATRIX", fontsize=10, fontname="hebo")
    page1.insert_text((50, 85), "Equipment: Continuous Wave Electron Spin Resonance (CW-ESR) Spectrometer", fontsize=9.5, fontname="helv")
    
    y = 115
    page1.draw_rect(fitz.Rect(50, y - 12, 545, y + 12), color=(0.2, 0.2, 0.2), fill=(0.9, 0.9, 0.9))
    page1.insert_text((55, y), "Sl. No.", fontsize=8.5, fontname="hebo")
    page1.insert_text((105, y), "Item Description / Technical Requirements", fontsize=8.5, fontname="hebo")
    page1.insert_text((440, y), "Compliance (Yes/No)", fontsize=8.5, fontname="hebo")
    
    sections_p1 = [
        ("1. Microwave Unit", [
            ("Microwave Bridge", [
                "Low-noise solid-state Gunn diode microwave source;",
                "Working frequency range: 9.2 GHz to 9.9 GHz (X-Band);",
                "Built-in electronic frequency counter with 1 kHz resolution;",
                "Microwave frequency stability: better than 10 kHz/hour;",
            ]),
            ("Microwave Power", [
                "Maximum leveled microwave output power: ≥ 200 mW;",
                "Unleveled maximum output power: up to 600 mW;",
                "Calibrated precision attenuator: 0 dB to 60 dB in 1 dB steps;",
                "Attenuation accuracy: ± 0.5 dB across operating band;",
            ]),
            ("Automatic Frequency Control (AFC)", [
                "AFC lock range: ± 5 MHz from resonator center frequency;",
                "AFC stability: 10^-6 frequency lock;",
                "Automatic AFC gain and phase control optimization;",
            ]),
        ]),
        ("2. Console & Signal Processing System", [
            ("Spectrometer Mainframe", [
                "Compact tower chassis with shielded power supply modules;",
                "Standard Ethernet TCP/IP interface for remote PC connection;",
            ]),
            ("Magnetic Field Controller", [
                "Field sweep range: -1 kG to +14 kG continuously adjustable;",
                "Field setting resolution: 18 bit (minimum 60 mG step size);",
                "Sweep time range: 320 µs to 5 s per field point;",
                "Short-term magnetic field stability: better than ± 5 mG;",
            ]),
            ("Signal Channel & Phase-Sensitive Detector", [
                "Modulation frequency synthesizer: 10 kHz and 100 kHz standard;",
                "Dual-phase digital lock-in amplifier with 0° and 90° simultaneous outputs;",
                "Digital integrating ADC with 18-bit signal amplitude resolution;",
                "Time constant selection: 0.01 ms to 5.0 seconds;",
            ]),
        ]),
    ]
    
    y = 135
    for unit_title, subsystems in sections_p1:
        # Unit Header Row
        page1.draw_rect(fitz.Rect(50, y - 5, 545, y + 14), fill=(0.94, 0.94, 0.94))
        page1.insert_text((55, y + 8), unit_title, fontsize=9.5, fontname="hebo")
        y += 22
        for sub_title, points in subsystems:
            # Subsystem Header Row
            page1.insert_text((70, y + 6), sub_title, fontsize=8.5, fontname="hebo")
            y += 16
            for pt in points:
                page1.insert_text((85, y + 5), f"•  {pt}", fontsize=8, fontname="helv")
                y += 14
            y += 4
        y += 8

    # Page 2: Magnets and Software
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 45), "ANNEXURE I (Continued) — TECHNICAL SPECIFICATIONS", fontsize=10, fontname="hebo")
    y = 75
    page2.draw_rect(fitz.Rect(50, y - 12, 545, y + 12), color=(0.2, 0.2, 0.2), fill=(0.9, 0.9, 0.9))
    page2.insert_text((55, y), "Sl. No.", fontsize=8.5, fontname="hebo")
    page2.insert_text((105, y), "Item Description / Technical Requirements", fontsize=8.5, fontname="hebo")
    page2.insert_text((440, y), "Compliance (Yes/No)", fontsize=8.5, fontname="hebo")
    
    sections_p2 = [
        ("3. Magnet Unit", [
            ("Electromagnet System", [
                "Nominal pole diameter: 6 inches (152 mm);",
                "Air gap: 35 mm to accommodate cryostat insertion;",
                "Maximum magnetic field strength: ≥ 0.85 Tesla (8500 Gauss);",
                "Field homogeneity: ± 10 ppm over 10 mm diameter spherical volume;",
            ]),
            ("Magnet Power Supply", [
                "2 kW ultra-low ripple regulated DC power supply;",
                "Current stability: ± 1 ppm per hour under thermal steady state;",
                "Overvoltage, water flow failure, and overtemperature protection circuits;",
            ]),
        ]),
        ("4. Workstation and Software Package", [
            ("Computer System", [
                "Pre-installed Linux Operating System with 64-bit real-time kernel;",
                "Intel Core i7 processor, 32 GB RAM, 1 TB NVMe SSD;",
                "High-resolution 27-inch LED display with minimum 2560 x 1440 resolution;",
            ]),
            ("Acquisition & Analysis Suite", [
                "Simultaneous 1D field sweep and 2D time/temperature/power 2D matrix;",
                "Real-time signal averaging, baseline correction, and peak picking;",
                "Spin concentration calibration and g-factor calculation algorithms;",
                "ASCII, CSV, and JCAMP-DX universal scientific export formats;",
            ]),
        ]),
    ]
    
    y = 95
    for unit_title, subsystems in sections_p2:
        page2.draw_rect(fitz.Rect(50, y - 5, 545, y + 14), fill=(0.94, 0.94, 0.94))
        page2.insert_text((55, y + 8), unit_title, fontsize=9.5, fontname="hebo")
        y += 22
        for sub_title, points in subsystems:
            page2.insert_text((70, y + 6), sub_title, fontsize=8.5, fontname="hebo")
            y += 16
            for pt in points:
                page2.insert_text((85, y + 5), f"•  {pt}", fontsize=8, fontname="helv")
                y += 14
            y += 4
        y += 8

create_pdf_with_drawings("03_deep_hierarchy_subsystems.pdf", build_deep_hierarchy_tender)

# -------------------------------------------------------------
# 4. Scanned / Rasterized Noisy OCR Tender (No Selectable Text)
# -------------------------------------------------------------
def build_scanned_noisy_tender():
    temp_doc = fitz.open()
    page = temp_doc.new_page(width=595, height=842)
    page.insert_text((60, 60), "LABORATORY INSTRUMENTATION TENDER", fontsize=14, fontname="hebo")
    page.insert_text((60, 80), "Schedule B: Technical Specifications with Special Characters", fontsize=10, fontname="helv")
    
    y = 120
    specs = [
        ("1", "Load Cell Capacity", "Maximum test force ≥ 50 kN with resolution of 0.01 N"),
        ("2", "Crosshead Speed", "Variable test velocity from 0.001 mm/min to 1000 mm/min ± 0.1%"),
        ("3", "Thermal Chamber", "Operating temperature range: -70 °C to +350 °C with ± 0.5 °C control"),
        ("4", "Extensometer Gauge", "Optical non-contact video extensometer gauge length 10 mm to 100 mm"),
        ("5", "Strain Accuracy", "Gauge resolution ≤ 0.5 µm conforming to ISO 9513 Class 0.5"),
        ("6", "Input Impedance", "Preamplifier input impedance ≥ 10 MΩ with leakage current ≤ 5 pA"),
        ("7", "RF Emission", "Conducted emissions complying with CISPR 11 Class A limits"),
        ("8", "Supply Voltage", "230 V ± 10% AC, 50 Hz single phase line input"),
    ]
    
    page.draw_rect(fitz.Rect(50, y - 15, 545, y + 15), fill=(0.88, 0.88, 0.88))
    page.insert_text((55, y), "Item", fontsize=9, fontname="hebo")
    page.insert_text((100, y), "Parameter", fontsize=9, fontname="hebo")
    page.insert_text((230, y), "Specification Requirement", fontsize=9, fontname="hebo")
    
    y = 150
    for sl, p, r in specs:
        page.draw_line((50, y + 15), (545, y + 15), color=(0.7, 0.7, 0.7), width=0.5)
        page.insert_text((55, y + 5), sl, fontsize=8.5, fontname="helv")
        page.insert_text((100, y + 5), p, fontsize=8.5, fontname="hebo")
        page.insert_text((230, y + 5), r, fontsize=8.5, fontname="helv")
        y += 32
        
    # Rasterize page to image at 150 DPI (simulates genuine scan with zero text layer)
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    temp_doc.close()
    
    # Create final PDF embedding only the rasterized image
    final_doc = fitz.open()
    scan_page = final_doc.new_page(width=595, height=842)
    scan_page.insert_image(fitz.Rect(0, 0, 595, 842), stream=img_bytes)
    outpath = os.path.join("stress-test-fixtures", "04_scanned_noisy_ocr.pdf")
    final_doc.save(outpath)
    final_doc.close()
    print(f"Generated: {outpath}")

build_scanned_noisy_tender()

# -------------------------------------------------------------
# 5. Adversarial Mixed Sections Tender (Commercial vs Technical)
# -------------------------------------------------------------
def build_adversarial_tender(doc):
    # Page 1: Commercial / Administrative (Must be rejected/ignored for requirements)
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "SECTION I: NOTICE INVITING TENDER & GENERAL INSTRUCTIONS", fontsize=12, fontname="hebo")
    p1.insert_text((50, 80), "1. Eligibility Criteria for Participating Bidders:", fontsize=10, fontname="hebo")
    commercial_terms = [
        "The bidder must have an annual average financial turnover of at least USD 5,000,000 over the past 3 years.",
        "The bidder shall deposit Earnest Money Deposit (EMD) of USD 25,000 in the form of Bank Guarantee.",
        "Bidder must submit audited balance sheets, GST registration, PAN copy, and Certificate of Incorporation.",
        "Non-compliance with tender submission guidelines will result in outright disqualification.",
        "Liquidated damages for delivery delay shall be levied at 0.5% per week up to a maximum of 10% of contract value.",
    ]
    y = 110
    for term in commercial_terms:
        p1.insert_text((50, y), f"•  {term}", fontsize=9, fontname="helv")
        y += 24
        
    # Page 2: Section IV - Technical Specifications (Must be routed and extracted)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "SECTION IV: TECHNICAL SPECIFICATIONS COMPLIANCE SHEET", fontsize=12, fontname="hebo")
    p2.insert_text((50, 70), "All equipment specifications below are mandatory requirements:", fontsize=9.5, fontname="helv")
    
    y = 100
    p2.draw_rect(fitz.Rect(50, y - 12, 545, y + 12), fill=(0.9, 0.92, 0.96))
    p2.insert_text((55, y), "Item", fontsize=8.5, fontname="hebo")
    p2.insert_text((90, y), "Subsystem Description", fontsize=8.5, fontname="hebo")
    p2.insert_text((240, y), "Technical Specification", fontsize=8.5, fontname="hebo")
    p2.insert_text((440, y), "Compliance (Yes/No)", fontsize=8.5, fontname="hebo")
    
    tech_specs = [
        ("1", "Vacuum Chamber", "Ultra-high vacuum chamber capable of base pressure ≤ 5 x 10^-10 mbar;"),
        ("2", "Turbomolecular Pump", "Magnetic levitation turbo pump with pumping speed ≥ 700 L/s for N2;"),
        ("3", "Ion Getter Pump", "Sputter ion pump with titanium sublimation combination ≥ 400 L/s;"),
        ("4", "Sample Manipulator", "Motorized 4-axis XYZ theta manipulator with 0.1 µm positional resolution;"),
        ("5", "Sample Heating", "E-beam heating stage capable of reaching up to 1200 °C continuously;"),
        ("6", "Low Temperature Cooling", "Integrated liquid helium continuous flow cryostat reaching < 10 Kelvin;"),
    ]
    y = 125
    for sl, subsys, spec in tech_specs:
        p2.draw_line((50, y + 14), (545, y + 14), color=(0.8, 0.8, 0.8), width=0.5)
        p2.insert_text((55, y + 6), sl, fontsize=8.5, fontname="helv")
        p2.insert_text((90, y + 6), subsys, fontsize=8.5, fontname="hebo")
        p2.insert_text((240, y + 6), spec, fontsize=8.5, fontname="helv")
        y += 26
        
    # Page 3: Financial Price Schedule (Must be excluded!)
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 50), "SECTION V: COMMERCIAL PRICE BID SCHEDULE (BOQ)", fontsize=12, fontname="hebo")
    p3.insert_text((50, 75), "Itemized pricing details (to be submitted in financial envelope only):", fontsize=9.5, fontname="helv")
    boq = [
        ("1", "Ultra-High Vacuum System Base Price", "USD", "150,000.00"),
        ("2", "Installation, Commissioning and On-site Testing", "USD", "15,000.00"),
        ("3", "Customs clearance, freight, insurance and port fees", "USD", "8,500.00"),
        ("4", "Annual Maintenance Contract (Years 4 and 5)", "USD", "20,000.00"),
    ]
    y = 110
    p3.draw_rect(fitz.Rect(50, y - 12, 545, y + 12), fill=(0.95, 0.9, 0.9))
    p3.insert_text((55, y), "Item", fontsize=8.5, fontname="hebo")
    p3.insert_text((90, y), "Commercial Line Item Description", fontsize=8.5, fontname="hebo")
    p3.insert_text((420, y), "Currency", fontsize=8.5, fontname="hebo")
    p3.insert_text((480, y), "Total Amount", fontsize=8.5, fontname="hebo")
    y = 135
    for item, desc, curr, amt in boq:
        p3.draw_line((50, y + 14), (545, y + 14), color=(0.8, 0.8, 0.8), width=0.5)
        p3.insert_text((55, y + 6), item, fontsize=8.5, fontname="helv")
        p3.insert_text((90, y + 6), desc, fontsize=8.5, fontname="helv")
        p3.insert_text((420, y + 6), curr, fontsize=8.5, fontname="helv")
        p3.insert_text((480, y + 6), amt, fontsize=8.5, fontname="helv")
        y += 26

create_pdf_with_drawings("05_adversarial_mixed_sections.pdf", build_adversarial_tender)
print("All 5 stress test PDFs generated successfully!")
