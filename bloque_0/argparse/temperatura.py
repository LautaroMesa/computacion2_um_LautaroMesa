import argparse


def celsius_a_fahrenheit(c):
    return c * 9 / 5 + 32


def fahrenheit_a_celsius(f):
    return (f - 32) * 5 / 9


def main():
    parser = argparse.ArgumentParser(
        description="Convierte temperaturas entre Celsius y Fahrenheit."
    )

    parser.add_argument(
        "valor",
        type=float,
        help="Temperatura a convertir",
    )
    parser.add_argument(
        "-t", "--to",
        choices=["celsius", "fahrenheit"],
        required=True,
        metavar="{celsius,fahrenheit}",
        help="Unidad de destino",
    )

    args = parser.parse_args()

    if args.to == "fahrenheit":
        resultado = celsius_a_fahrenheit(args.valor)
        print(f"{args.valor:g}°C = {resultado:.1f}°F")
    else:
        resultado = fahrenheit_a_celsius(args.valor)
        print(f"{args.valor:g}°F = {resultado:.2f}°C")


if __name__ == "__main__":
    main()