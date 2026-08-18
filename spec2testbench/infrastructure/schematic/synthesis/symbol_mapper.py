import schemdraw.elements as elm


class SymbolMapper:
    def make(self, component):
        label = component.name

        if component.value:
            label += f"\n{component.value}"

        kind = component.kind.upper()

        if kind == "R":
            return elm.Resistor().label(label)
        if kind == "C":
            return elm.Capacitor().label(label)
        if kind == "L":
            return elm.Inductor().label(label)
        if kind == "V":
            return elm.SourceV().label(label)
        if kind == "I":
            return elm.SourceI().label(label)
        if kind == "D":
            return elm.Diode().label(label)
        if kind == "M":
            if component.model and "p" in component.model.lower():
                return elm.PFet().label(label)
            return elm.NFet().label(label)
        if kind == "E":
            return elm.Opamp().label(label)
        if kind == "B":
            return elm.RBox().label(label)

        return elm.RBox().label(label)