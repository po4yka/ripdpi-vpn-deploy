class Summary:
    def __init__(self, title):
        self.title = str(title)
        self._rows = []

    @classmethod
    def new(cls, title):
        return cls(title)

    def add(self, key, value):
        self._rows.append((str(key), str(value)))
        return self

    def rows(self):
        return tuple(self._rows)

    def render(self):
        print()
        print(self.title)
        for key, value in self._rows:
            print(f"  {key}: {value}")
