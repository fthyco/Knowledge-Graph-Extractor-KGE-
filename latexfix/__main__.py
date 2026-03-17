"""
__main__.py — Command-line interface for latexfix.

Usage:
    python -m latexfix input.md [output.md]
"""

import sys
import argparse
from pathlib import Path
from .pipeline import LatexFix

def main():
    parser = argparse.ArgumentParser(description="Fix broken LaTeX matrices in Markdown files extracted from PDFs.")
    parser.add_argument("input_file", help="Path to the input Markdown file")
    parser.add_argument("output_file", nargs="?", help="Path to save the fixed Markdown file (optional, defaults to input_fixed.md)")
    parser.add_argument("--decimals", type=int, default=5, help="Number of decimal places for rendered matrices")
    parser.add_argument("--no-auto-solve", action="store_true", help="Disable automatic solving of X'X and X'y pairs")
    
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)
        
    print(f"Reading and detecting matrices in {input_path}...")
    try:
        lf = LatexFix(str(input_path)).run()
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)
        
    print(lf.report())
    
    if not args.no_auto_solve and len(lf.matrices) > 0:
        print("Running automatic computations...")
        try:
            solutions = lf.auto_solve()
            if solutions:
                print(f"  ✓ Automatically computed {len(solutions)} operation(s).")
        except Exception as e:
            print(f"  Warning: Auto-solve failed: {e}")
    
    if not args.output_file:
        out_path = input_path.with_name(f"{input_path.stem}_fixed{input_path.suffix}")
    else:
        out_path = Path(args.output_file)
        
    print(f"Saving fixed document to {out_path}...")
    try:
        lf.save(str(out_path), decimals=args.decimals)
        print("Done!")
    except Exception as e:
        print(f"Error saving file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
