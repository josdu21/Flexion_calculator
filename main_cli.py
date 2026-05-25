#!/usr/bin/env python3
"""
Interfaz CLI - Sin dependencias externas
Ejecutar: python main_cli.py
"""

from core.units import UnitSystem, get_converter
from core.flexion import BeamSection
from core.bar_tables import suggest_bar_combinations

def print_header(title):
    print("\n" + "=" * 60)
    print(f"{title:^60}")
    print("=" * 60)

def print_section(title):
    print(f"\n{title}")
    print("-" * 60)

def get_unit_system():
    print_header("CALCULADORA DE ACERO POR FLEXIÓN - ACI 318-19")
    print("\nSistemas de unidades disponibles:")
    for i, system in enumerate(UnitSystem, 1):
        print(f"  {i}. {system.value}")

    while True:
        try:
            choice = int(input("\nSelecciona el sistema (1-3): "))
            return list(UnitSystem)[choice - 1]
        except (ValueError, IndexError):
            print("Opción inválida. Intenta de nuevo.")

def get_section_type():
    print("\n¿Qué deseas calcular?")
    print("  1. Viga")
    print("  2. Losa (franja unitaria)")

    while True:
        try:
            choice = int(input("\nSelecciona (1-2): "))
            return choice == 2
        except ValueError:
            print("Opción inválida.")

def get_input(label, default=None):
    prompt = f"{label}"
    if default is not None:
        prompt += f" (default: {default}): "
    else:
        prompt += ": "

    while True:
        try:
            value = input(prompt).strip()
            if not value and default is not None:
                return default
            return float(value)
        except ValueError:
            print("Valor inválido. Ingresa un número.")

def get_inputs(unit_system, is_slab=False):
    converter = get_converter(unit_system)

    print_section("INGRESA LOS DATOS DE LA SECCIÓN")

    mu = get_input(f"Momento último Mu [{converter.moment_unit}]", 150)

    if is_slab:
        b = 1.0  # Fixed at 1 m for unit strip
        print(f"Ancho (b) = 1.0 m (franja unitaria automática)")
    else:
        b = get_input(f"Ancho (b) [{converter.length_unit}]", 0.3)

    h = get_input(f"Altura total (h) [{converter.length_unit}]", 0.5)
    cover = get_input(f"Recubrimiento libre [{converter.length_unit}]", 0.04)

    # Default values for f'c and fy based on unit system
    if unit_system == UnitSystem.SI:
        fc_default, fy_default = 28, 420
    elif unit_system == UnitSystem.MKS:
        fc_default, fy_default = 280, 4200
    else:  # ENGLISH
        fc_default, fy_default = 4000, 60000

    fc = get_input(f"f'c [{converter.stress_unit}]", fc_default)
    fy = get_input(f"fy [{converter.stress_unit}]", fy_default)

    # Convert to SI
    return {
        "mu_nmm": mu * converter.moment_to_knm * 1e6,
        "b_mm": b * converter.length_to_m * 1000,
        "h_mm": h * converter.length_to_m * 1000,
        "cover_mm": cover * converter.length_to_m * 1000,
        "fc_mpa": fc * converter.stress_to_mpa,
        "fy_mpa": fy * converter.stress_to_mpa,
    }

def display_results(result, is_slab=False):
    print_section("RESULTADOS DEL DISEÑO (ACI 318-19)")

    print(f"\nGEOMETRÍA")
    print(f"  d (peralte efectivo):     {result.d_mm:.2f} mm")
    print(f"  a (bloque Whitney):       {result.a_mm:.2f} mm")
    print(f"  c (eje neutro):           {result.c_mm:.2f} mm")
    print(f"  jd (brazo de palanca):    {result.jd_mm:.2f} mm")
    print(f"  β₁:                       {result.beta_1:.4f}")

    print(f"\nACERO")
    print(f"  ρ requerida:              {result.rho_required:.4f}")
    print(f"  As requerido:             {result.as_required_cm2:.2f} cm²")
    print(f"  As mínimo:                {result.as_min_cm2:.2f} cm²")
    print(f"  As máximo:                {result.as_max_cm2:.2f} cm²")
    print(f"  As proporcionado:         {result.as_provided_cm2:.2f} cm²")
    print(f"  ρ proporcionada:          {result.rho_provided:.4f}")

    print(f"\nFUERZAS INTERNAS")
    print(f"  C (compresión):           {result.compression_kn:.2f} kN")
    print(f"  T (tensión):              {result.tension_kn:.2f} kN")

    print(f"\nCAPACIDAD vs DEMANDA")
    print(f"  φMn:                      {result.phi_mn_knm:.2f} kN·m")
    print(f"  Mu:                       {result.mu_demand_knm:.2f} kN·m")
    ratio = result.phi_mn_knm / result.mu_demand_knm if result.mu_demand_knm > 0 else 0
    print(f"  φMn/Mu:                   {ratio:.2f}")

    # Status with visual indicator
    status_map = {
        "OK": "✓ OK",
        "AUMENTAR SECCIÓN": "✗ AUMENTAR SECCIÓN",
        "REDUCIR SECCIÓN": "✗ REDUCIR SECCIÓN",
        "ARMADO INSUFICIENTE": "✗ ARMADO INSUFICIENTE",
    }

    print(f"\nESTADO")
    print(f"  {status_map.get(result.status, result.status)}")

    if result.warnings:
        print(f"\nADVERTENCIAS")
        for w in result.warnings:
            print(f"  ⚠ {w}")

    print_section("SUGERENCIAS DE VARILLAS")
    as_demand = max(result.as_required_cm2, result.as_min_cm2)
    combinations = suggest_bar_combinations(as_demand, max_suggestions=3)
    for i, combo in enumerate(combinations, 1):
        print(f"  {i}. {combo.description}")

    print()

def main():
    try:
        # Get configuration
        unit_system = get_unit_system()
        is_slab = get_section_type()

        section_type = "LOSA (FRANJA UNITARIA)" if is_slab else "VIGA"

        # Get inputs
        values = get_inputs(unit_system, is_slab)

        # Calculate
        print(f"\nCalculando {section_type}...")
        section = BeamSection(**values)
        result = section.design()

        # Display results
        display_results(result, is_slab)

        # Ask if continue
        while True:
            again = input("¿Calcular otra sección? (s/n): ").lower().strip()
            if again in ["s", "si", "sí", "yes", "y"]:
                main()
                return
            elif again in ["n", "no"]:
                print("\n¡Gracias por usar la Calculadora de Acero por Flexión!")
                return
            else:
                print("Ingresa 's' para sí o 'n' para no.")

    except KeyboardInterrupt:
        print("\n\nPrograma interrumpido por el usuario.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
