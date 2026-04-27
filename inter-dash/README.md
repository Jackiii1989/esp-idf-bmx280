# inter-dash

A reactive dashboard for small jet engine combustor calculations  that does air mass flow,
compressor performance, propane run time, and equivalence ratio. Built with
[Marimo](https://marimo.io).

---

## What it does

- Calculates **air mass flow** from compressor geometry and operating conditions using the Euler turbomachinery equations
- Computes **pressure ratio**, **tip speed**, and **compressor exit temperature** step by step
- Estimates **propane run time** from 200 g canisters across a range of equivalence ratios
- Shows the full calculation with live values substituted at every step as you move the sliders


## Requirements

- Python **3.12 or newer**
- [uv](https://docs.astral.sh/uv/) — Python package manager


## Installation

### 1. Install uv (Windows)

Open **PowerShell** and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen PowerShell after installation so the `uv` command is available.

Verify it worked:

```powershell
uv --version
```

### 2. Clone or copy the project

### 3. Install dependencies

```powershell
uv sync
```

This reads the `pyproject.toml` and installs everything automatically into an isolated environment. You only need to do this once.

## Running the app

```powershell
uv run marimo edit m-air-calculation.py
```

This opens the dashboard in your browser. All sliders are live — moving one instantly updates all calculations and the step-by-step display below.

Marimo will open the app automatically in your default browser at`http://localhost:2718`.


> **App view mode:** when pressing in the lower right corner the app view button, the experience and rending is better. 

## Project structure

```
inter-dash/
├── m-air-calculation.py    # the marimo app — all calculations and UI
├── pyproject.toml   		# project metadata and dependencies
└── README.md        		# this file
```

---

## What the app calculates

| Section | What it does |
|---|---|
| **Compressor geometry** | Set wheel diameter, inlet eye diameter, number of stages |
| **Operating conditions** | RPM, ambient temperature, ambient pressure |
| **Compressor performance** | Efficiency η, slip factor σ, flow coefficient φ_flow |
| **Results** | Air mass flow, tip speed, pressure ratio, compressor exit temperature |
| **Step-by-step** | Every formula shown live with your actual slider values substituted in |
| **Propane run time** | Number of 200 g canisters × equivalence ratio → run time table |
| **Reference accordion** | Formula table, explanation of φ_flow, slip factor, how to measure RPM |

## Physics background

The compressor model is based on the **Euler turbomachinery equations** and
isentropic relations for a perfect gas.

## Key parameters explained

| Parameter | Typical range | Description |
|---|---|---|
| D_eye | 50–150 mm | Outer diameter of the compressor disc |
| D_hub | 35–65% of D_eye | Inlet opening diameter — measure with a calliper |
| RPM | 80 000–150 000 | Rotational speed — 109 000 typical for 70 mm wheel |
| η (efficiency) | 65–80 % | How well the compressor converts blade work to pressure |
| σ (slip factor) | 0.85–0.92 | How well the air follows the blade tip |
| φ_flow | 0.18–0.28 | Axial velocity as fraction of tip speed |
| φ (equivalence ratio) | 0.30–0.65 | Fuel-to-air ratio relative to stoichiometric |

### Constants used

| Symbol | Description | Value |
|---|---|---|
| cp | Specific heat of air at constant pressure | 1005 J/(kg·K) |
| γ | Ratio of specific heats for air | 1.4 |
| R | Specific gas constant for air | 287 J/(kg·K) |
| AFR_stoich | Stoichiometric air-fuel ratio for propane | 15.6 kg_air / kg_fuel |
| LHV | Lower heating value of propane | 46 300 kJ/kg |

## Troubleshooting

**`uv` is not recognised after installation**
Close and reopen PowerShell. If it still does not work, restart your computer.

**Browser does not open automatically**
Copy the URL printed in the terminal (usually `http://localhost:2718`) and paste it into your browser manually.

**`uv sync` fails with a Python version error**
Make sure Python 3.12 or newer is installed. Check with:
```powershell
python --version
```
If not installed, `uv` can install it for you:
```powershell
uv python install 3.12
```

---

## Notes for collaborators

- All calculations are in **SI units** internally. Inputs in mm and mbar are
  converted to m and Pa before any formula is applied.
- The air mass flow result is an **estimate** based on the Euler model. It should
  be validated against a measured orifice plate reading once the rig is built.
- Do not change the cell execution order in Marimo edit mode — cells depend on
  each other in a specific sequence.
- The step-by-step cell uses Python f-strings with LaTeX inside. If you edit a
  variable name in the calculation cell, update the corresponding name in the
  step-by-step cell too or the app will crash.

---

## References

- Antoshkiv et al. (2017) — ignition physics and propane combustion data
- Lefebvre A.H. (1999) — *Gas Turbine Combustion*, Taylor & Francis
- NIST Chemistry WebBook — propane thermodynamic properties
- Euler turbomachinery equation — standard result, see any turbomachinery textbook
