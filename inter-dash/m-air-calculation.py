import marimo

__generated_with = "0.23.3"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import math

    return math, mo


@app.function(hide_code=True)
def fmt_time(s):
    if s < 60:
        return f"{s:.0f} s"
    elif s < 3600:
        return f"{s / 60:.1f} min"
    else:
        return f"{s / 3600:.2f} hr"


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Jet Engine — Air Flow & Run Time Calculator

    **Compressor model based on Euler turbomachinery equations**
    `cp = 1005 J/kg·K  ·  γ = 1.4  ·  R = 287 J/kg·K  ·  AFR_stoich (propane) = 15.6`
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Compressor geometry
    """)
    return


@app.cell
def _(mo):
    sl_de = mo.ui.slider(
        start=30,
        stop=150,
        step=1,
        value=70,
        label="Wheel diameter D_eye (mm)",
        show_value=True,
    )
    sl_dh = mo.ui.slider(
        start=15,
        stop=120,
        step=1,
        value=42,
        label="Inlet eye diameter D_hub (mm)",
        show_value=True,
    )
    sl_st = mo.ui.slider(
        start=1,
        stop=3,
        step=1,
        value=1,
        label="Number of compressor stages",
        show_value=True,
    )
    mo.vstack([sl_de, sl_dh, sl_st])
    return sl_de, sl_dh, sl_st


@app.cell
def _(mo):
    img = mo.image(src="img/compressor_inlet_black_text.svg")
    img.style(width="400px", height="auto")
    return


@app.cell
def _(mo):
    mo.md("""
    ## Operating conditions
    """)
    return


@app.cell
def _(mo):
    sl_rpm = mo.ui.slider(
        start=10_000,
        stop=200_000,
        step=1_000,
        value=10_000,
        label="Rotational speed (RPM)",
        show_value=True,
    )
    sl_T = mo.ui.slider(
        start=-20,
        stop=50,
        step=1,
        value=20,
        label="Ambient temperature (°C)",
        show_value=True,
    )
    sl_P = mo.ui.slider(
        start=800,
        stop=1_050,
        step=1,
        value=1_013,
        label="Ambient pressure (mbar)",
        show_value=True,
    )
    mo.vstack([sl_rpm, sl_T, sl_P])
    return sl_P, sl_T, sl_rpm


@app.cell
def _(mo):
    mo.md("""
    ## Compressor performance
    """)
    return


@app.cell
def _(mo):
    sl_eta = mo.ui.slider(
        start=50,
        stop=92,
        step=1,
        value=75,
        label="Isentropic efficiency η (%), the compressor is not perfect for calculating how much the T raised",
        show_value=True,
    )
    sl_sig = mo.ui.slider(
        start=0.70,
        stop=0.98,
        step=0.01,
        value=0.90,
        label="Slip factor σ  (typical 0.85–0.92), the air slips over the bladed it does perfectly grab",
        show_value=True,
    )
    sl_phi_flow = mo.ui.slider(
        start=0.10,
        stop=0.40,
        step=0.01,
        value=0.22,
        label="Flow coefficient φ_flow  (axial velocity / tip speed, convert from Utip to axial speed, typical 0.18–0.28)",
        show_value=True,
    )
    mo.vstack([sl_eta, sl_sig, sl_phi_flow])
    return sl_eta, sl_phi_flow, sl_sig


@app.cell
def _(
    math,
    sl_P,
    sl_T,
    sl_de,
    sl_dh,
    sl_eta,
    sl_phi_flow,
    sl_rpm,
    sl_sig,
    sl_st,
):
    # CONSTANTS ----------------------------------------------------------------------------------------

    # NEED TO CALCUKLATE PRESSURE DROP
    # How much energy does it take to heat 1 kg of air by 1 degree?
    # The answer for air is 1005 Joules. That is cp — the specific heat at constant pressure.
    # 1005 J/(kg·K) — specific heat of air

    # In the compressor, the blades do mechanical work on the air. That work shows up as heat — the air gets hotter. # cp tells you the conversion rate: how many degrees of temperature rise you get per Joule of work added per  kilogram.
    cp = 1005.0

    # Air can store energy in two ways: by heating up (cp) and by changing volume at constant temperature (cv). γ is simply their ratio between them. The higher gam is, the more pressure you get for a give temperature rise.
    # For air, γ = 1.4 is a fixed constant at normal temperatures. For exhaust gases (hotter, more complex molecules) γ drops to around 1.33.
    # IT IS a very important part for calculating the pressure ratio
    gam = 1.4


    # NEED to calculate air density
    # specific gas constant for air, R = 287 J/kg·K
    R = 287.0

    # EQUATIONS ----------------------------------------------------------------------------------------

    # diameter wheel
    De = sl_de.value / 1000.0
    # diameter eye
    Dh = sl_dh.value / 1000.0
    # number of compressor stages
    st = sl_st.value
    # revolution per minute
    rpm = sl_rpm.value

    # Ambient temperature # C → K
    T1 = sl_T.value + 273.15
    # Ambient pressure, # mbar → Pa
    P1 = sl_P.value * 100.0
    # isotropic coeficient
    eta = sl_eta.value / 100.0
    # slip factor
    sig = sl_sig.value
    # flow coefficient from U_tip to V_axial
    phiF = sl_phi_flow.value

    # calculating U_tip
    omega = rpm * 2 * math.pi / 60
    U_tip = omega * De / 2

    # EULER TURBOMACHINERY EQUATION
    # the six lines describe what happens to air inside the compressor. The compressor spins and squeezes air.
    # These equations tell you by exactly how much, and at what cost in temperature
    # the work done by per kilogram is proportional to U_tip²
    # the slip factor accounts that the air not perfectly follows the blade. It slips slighty, so get a little less work then ideal. It will give how many JOULES/kg we generate. This is work.
    W_euler = sig * U_tip**2 * st

    # The ideal temperature rise in a perfect compressor. W_euler is work done per kilogram, now divide it let find how many degrees are changing in PERFECT LOSSLESS COMPRESSOR
    dT_ideal = W_euler / cp

    # this part "** (gam / (gam - 1))" is what makes the compression so powerful in the compression ratio equation.
    # A relavitely small temperature rasio produces amuch larger pressure ratio, because of that 3.5 power. ( gam/(gam−1) = 1.4/0.4 = 3.5 )
    compressor_ratio = gam / (gam - 1)

    # the pressure ratio, It is the isentropic relation. It connect temperature rise to pressure rise for a compressible gas,
    PR = (1 + eta * dT_ideal / T1) ** compressor_ratio

    # DELTA T LOSS
    # the real temperature rise in a compressor with a loss eta. A real compressor is not perfect.
    # Friction, turbolance, flow separation waste on the blade work as heat instead of useful pressure rise.
    # The efficiency η (typically 0.70–0.80 for small compressors) captures this.
    dT_actual = dT_ideal / eta

    # The actual exit temperature
    T2 = T1 + dT_actual

    # The actual exit temperature
    P2 = P1 * PR

    # air density changes depending on the Temperature and depending on the pressure
    p_air = P1 / (R * T1)

    # surface of the air flows in the jet engine.
    A_eye = math.pi / 4 * (De**2 - Dh**2)

    # speed of air flow
    V_axial = phiF * U_tip

    # final equation, m_air_flow = p_air_density * surface_of_air_flow * speed_of_of_air_flow
    mdot = p_air * A_eye * V_axial

    mdot_gs = mdot * 1000.0

    warnings = []
    if U_tip > 500:
        warnings.append(
            f"Tip speed {U_tip:.0f} m/s exceeds safe limit for steel (~500 m/s). Reduce RPM."
        )
    if Dh >= De:
        warnings.append("Hub diameter must be smaller than Eye diameter.")
    if V_axial > 200:
        warnings.append(
            f"Inlet axial velocity {V_axial:.0f} m/s is very high — check flow coefficient."
        )
    if PR > 5:
        warnings.append(
            f"Pressure ratio {PR:.1f} is high for a single-stage compressor (typical max 3–4)."
        )
    return (
        A_eye,
        De,
        Dh,
        P1,
        PR,
        T1,
        T2,
        U_tip,
        V_axial,
        W_euler,
        dT_actual,
        dT_ideal,
        eta,
        mdot_gs,
        p_air,
        phiF,
        rpm,
        sig,
        st,
        warnings,
    )


@app.cell
def _(PR, T2, U_tip, dT_actual, mdot_gs, mo, warnings):
    if warnings:
        status = mo.callout(
            mo.md("**Warnings:**\n\n" + "\n\n".join(f"⚠ {w}" for w in warnings)),
            kind="warn",
        )
    else:
        status = mo.callout(
            mo.md(
                "✓ Parameters look physically reasonable for a small centrifugal compressor."
            ),
            kind="success",
        )

    stats = mo.hstack(
        [
            mo.stat(
                value=f"{mdot_gs:.1f} g/s",
                label="Air mass flow",
                caption=f"{mdot_gs * 3.6:.2f} kg/hr",
            ),
            mo.stat(
                value=f"{U_tip:.0f} m/s",
                label="Tip speed",
                caption="max ~500 m/s (steel)",
            ),
            mo.stat(value=f"{PR:.2f}", label="Pressure ratio", caption="P2 / P1"),
            mo.stat(
                value=f"{dT_actual:.0f} K",
                label="Compressor ΔT",
                caption=f"T_exit = {T2 - 273.15:.0f} °C",
            ),
        ],
        justify="space-between",
    )

    mo.vstack(
        [
            mo.md("## Results"),
            status,
            stats,
        ]
    )
    return


@app.cell
def _(
    A_eye,
    De,
    Dh,
    P1,
    PR,
    T1,
    T2,
    U_tip,
    V_axial,
    W_euler,
    dT_ideal,
    eta,
    mdot_gs,
    mo,
    p_air,
    phiF,
    rpm,
    sig,
    st,
):
    mo.md(f"""
    ## Step-by-step calculation

    **Step 1 — Tip speed**
    $U_{{tip}} = \\frac{{\\pi \\times D_{{wheel}} \\times N}}{{60}}
    = \\frac{{\\pi \\times {De * 1000:.0f}\\ \\text{{mm}} \\times {rpm:,}}}{{60}}
    = {U_tip:.1f}\\ \\text{{m/s}}$

    **Step 2 — Euler work input**
    $W = \\sigma \\times U_{{tip}}^2 \\times \\text{{stages}}
    = {sig:.2f} \\times {U_tip:.1f}^2 \\times {st}
    = {W_euler:.0f}\\ \\text{{J/kg}}$

    **Step 3 — Ideal temperature rise**
    $\\Delta T_{{ideal}} = \\frac{{W}}{{c_p}}
    = \\frac{{{W_euler:.0f}}}{{1005}}
    = {dT_ideal:.1f}\\ \\text{{K}}$

    **Step 4 — Pressure ratio**
    $PR = \\left(1 + \\frac{{\\eta \\cdot \\Delta T_{{ideal}}}}{{T_1}}\\right)^{{\\gamma/(\\gamma-1)}}
    = \\left(1 + \\frac{{{eta:.2f} \\times {dT_ideal:.1f}}}{{{T1:.1f}}}\\right)^{{3.5}}
    = {PR:.3f}$

    **Step 5 — Actual exit temperature**
    $T_2 = T_1 + \\frac{{\\Delta T_{{ideal}}}}{{\\eta}}
    = {T1:.1f} + \\frac{{{dT_ideal:.1f}}}{{{eta:.2f}}}
    = {T2:.1f}\\ \\text{{K}} = {T2 - 273.15:.0f}\\ °\\text{{C}}$

    **Step 6 — Inlet air density**
    $\\rho_1 = \\frac{{P_1}}{{R \\cdot T_1}}
    = \\frac{{{P1:.0f}}}{{287 \\times {T1:.1f}}}
    = {p_air:.4f}\\ \\text{{kg/m}}^3$

    **Step 7 — Inlet eye area**
    $A_{{eye}} = \\frac{{\\pi}}{{4}} \\times (D_{{eye}}^2 - D_{{hub}}^2)
    = \\frac{{\\pi}}{{4}} \\times (\\left({De * 1000:.0f}\\ \\text{{mm}}\\right)^2 - \\left({Dh * 1000:.0f}\\ \\text{{mm}}\\right)^2)
    = {A_eye * 1e6:.1f}\\ \\text{{mm}}^2$

    **Step 8 — Axial inlet velocity**
    $C_a = \\phi_{{flow}} \\times U_{{tip}}
    = {phiF:.2f} \\times {U_tip:.1f}
    = {V_axial:.1f}\\ \\text{{m/s}}$

    **Step 9 — Air mass flow**
    $\\dot{{m}}_{{air}} = \\rho_1 \\times A_{{eye}} \\times C_a
    = {p_air:.4f} \\times {A_eye:.6f} \\times {V_axial:.1f}
    = \\mathbf{{{mdot_gs:.2f}\\ \\text{{g/s}}}}$
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Propane run time
    """)
    return


@app.cell
def _(mo):
    sl_cans = mo.ui.slider(
        start=1,
        stop=20,
        step=1,
        value=1,
        label="Number of 200 g canisters",
        show_value=True,
    )
    sl_eqr = mo.ui.slider(
        start=0.10,
        stop=1.20,
        step=0.01,
        value=0.40,
        label="Equivalence ratio φ",
        show_value=True,
    )
    sl_uf = mo.ui.slider(
        start=60,
        stop=95,
        step=1,
        value=80,
        label="Usable fraction (%)",
        show_value=True,
    )
    mo.vstack([sl_cans, sl_eqr, sl_uf])
    return sl_cans, sl_eqr, sl_uf


@app.cell
def _(mdot_gs, mo, sl_cans, sl_eqr, sl_uf):
    AFR_STOICH = 15.6
    LHV = 46_300.0

    cans = sl_cans.value
    eqr = sl_eqr.value
    uf = sl_uf.value / 100.0

    usable = cans * 200.0 * uf
    mfuel = (eqr * mdot_gs) / AFR_STOICH
    tsec = usable / mfuel
    power = (mfuel / 1000.0) * LHV

    rt_stats = mo.hstack(
        [
            mo.stat(
                value=fmt_time(tsec), label="Run time", caption=f"{tsec:.0f} s total"
            ),
            mo.stat(
                value=f"{mfuel:.2f} g/s", label="Fuel flow", caption=f"φ = {eqr:.2f}"
            ),
            mo.stat(
                value=f"{usable:.0f} g",
                label="Usable propane",
                caption=f"{cans} × 200 g × {sl_uf.value}%",
            ),
            mo.stat(
                value=f"{power:.1f} kW",
                label="Thermal power",
                caption="LHV = 46.3 MJ/kg",
            ),
        ],
        justify="space-between",
    )

    draw_warn = (
        mo.callout(
            mo.md(
                f"⚠ Draw rate **{mfuel:.1f} g/s** may be too high for "
                f"{cans} × 200 g canister{'s' if cans > 1 else ''}. "
                "The bottle will chill. Use more canisters or a larger bottle."
            ),
            kind="warn",
        )
        if mfuel > cans * 8.0
        else mo.md("")
    )

    rows = []
    for phi_v in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80, 1.00]:
        mf = (phi_v * mdot_gs) / AFR_STOICH
        rows.append(
            {
                "φ": f"{phi_v:.2f}",
                "fuel flow (g/s)": f"{mf:.2f}",
                f"run time ({cans} can{'s' if cans > 1 else ''})": fmt_time(
                    usable / mf
                ),
                "thermal power (kW)": f"{(mf / 1000) * LHV:.1f}",
            }
        )

    mo.vstack(
        [
            rt_stats,
            draw_warn,
            mo.md("### Run time across equivalence ratios"),
            mo.ui.table(rows, selection=None),
            mo.md(
                f"**Formula:** t = (n × 200 g × {sl_uf.value}%) × 15.6 / (φ × ṁ_air)"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Formula reference": mo.md("""
    | Symbol | Description | Formula |
    |--------|-------------|---------|
    | U_tip | Blade tip speed | π × D_wheel × RPM / 60 |
    | W | Euler work per stage | σ × U_tip² |
    | ΔT_ideal | Ideal temperature rise | W / cp |
    | PR | Pressure ratio | (1 + η × ΔT / T1)^(γ/(γ-1)) |
    | ρ1 | Inlet density | P1 / (R × T1) |
    | A_eye | Eye area | π/4 × D_eye² |
    | Ca | Axial velocity | φ_flow × U_tip |
    | ṁ_air | Air mass flow | ρ1 × A_eye × Ca |
    | ṁ_fuel | Fuel flow | φ × ṁ_air / 15.6 |
    | t_run | Run time | m_usable / ṁ_fuel |
    | P_thermal | Thermal power | ṁ_fuel × LHV |

    **Constants:** cp = 1005 J/kg·K · γ = 1.4 · R = 287 J/kg·K
    **Propane:** AFR_stoich = 15.6 · LHV = 46 300 kJ/kg
        """),
            "What is the flow coefficient φ_flow?": mo.md("""
    φ_flow = axial inlet velocity / tip speed.

    - **0.15–0.18** — slow inlet, high pressure ratio, risk of stall
    - **0.20–0.25** — normal operation for small jets
    - **0.28–0.35** — high flow, lower pressure ratio, risk of choke

    For your 70 mm engine start at **0.22** as a baseline.
        """),
            "What is the slip factor σ?": mo.md("""
    σ accounts for the gas not perfectly following the blade at the tip.

    - σ = 1.0 — perfect (impossible)
    - σ = 0.85–0.92 — well-designed centrifugal compressor
    - σ = 0.80 — simple blade profiles

    Stanitz estimate: σ ≈ 1 − 0.63π / n_blades
        """),
            "How to measure RPM without a spec sheet": mo.md("""
    For your 70 mm wheel, estimate design RPM from tip speed:

    - Target tip speed: **350–450 m/s** for good efficiency
    - N = U_tip × 60 / (π × D_wheel)
    - At 400 m/s: N = 400 × 60 / (π × 0.070) ≈ **109 000 RPM**

    To measure directly once running:
    - Optical tachometer (cheap, laser-based)
    - Hall effect sensor on shaft + ESP32-S3 pulse counter
    - ESC telemetry (if electrically started)
        """),
        }
    )
    return


if __name__ == "__main__":
    app.run()
