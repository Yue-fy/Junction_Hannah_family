import sys

from stoa.eval.runner import main

if __name__ == "__main__":
    if "--list" in sys.argv:
        from stoa.solvers import available, import_errors

        print("solvers:", ", ".join(available()))
        for mod, tb in import_errors().items():
            print(f"[import error] {mod}\n{tb}")
        sys.exit(0)
    sys.exit(main())
