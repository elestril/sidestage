import subprocess
import shutil

def test_pyright():
    """
    Runs pyright to check for type errors in the codebase.
    Fails if pyright returns a non-zero exit code.
    """
    # Check if pyright is available
    pyright_path = shutil.which("pyright")
    if not pyright_path:
        # Fallback to running via poetry if not in path (though running via poetry pytest usually has it)
        # We assume 'pyright' executable is available in the environment
        pass
        
    result = subprocess.run(
        ["pyright", "--warnings"], 
        capture_output=True,
        text=True
    )
    
    # Print output if there's an error to help debugging
    if result.returncode != 0:
        print("\nPyright Errors:\n")
        print(result.stdout)
        print(result.stderr)
        
    assert result.returncode == 0, "Pyright found type errors. See stdout for details."
