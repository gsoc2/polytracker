#!/usr/bin/env python3.7

"""
  This code is inspired by Angora's angora-clang
  which is a modification of AFL's LLVM mode
 
  We do not use any of the AFL internal macros/instrumentation
 
  This is a compiler wrapper around gllvm, but wllvm will also work
 
  The workflow is to build a project using the build setting, then you can extract all the bitcode you want
 
  llvm-link the bitcode together into a whole program archive
 
  Then you can use polybuild(++) --instrument -f program.bc -o output -llib1 -llib2
 
  It will run opt to instrument your bitcode and then compile/link all instrumentation libraries with clang to create your output exec.
 
  Part of the reason this isnt a fully automated process is it allows users to easily build complex projects with multiple DSOs without accidentally linking
  against the compiler-rt based runtime pre_init_array. This allows the user to extract BC for whatever DSOs and executables they want, while still being
  able to easily include other libraries they did not want tracking in.
"""
import argparse
import os
import sys

from typing import List, Optional

from dataclasses import dataclass


@dataclass
class CompilerMeta:
    is_cxx: bool
    compiler_dir: str


class PolyBuilder:
    def __init__(self, is_cxx):
        self.meta = CompilerMeta(is_cxx, self.poly_find_dir(os.path.realpath(__file__)) + "/")

    def poly_check_cxx(self, compiler: str) -> bool:
        """
        Checks if compiling a c++ or c program
        """
        print(compiler)
        if compiler.find("++") != -1:
            return True
        return False

    def poly_find_dir(self, compiler_path: str) -> str:
        """
        Discover compiler install directory
        Checks to see if the path is local directory, if not gives the entire path
        """
        last_slash: int = compiler_path.rfind("/")
        if last_slash == -1:
            return "."
        return compiler_path[0:last_slash]

    def poly_is_linking(self, argv) -> bool:
        nonlinking_options = ["-E", "-fsyntax-only", "-S", "-c"]
        for option in argv:
            if option in nonlinking_options:
                return False
        return True

    def poly_add_inst_lists(self, directory: str) -> Optional[List[str]]:
        """
        Adds a directory of lists to the instrumentation
        """
        dir_path = self.meta.compiler_dir + "../abi_lists/" + directory + "/"
        print(dir_path)
        file_list = []
        if not os.path.exists(dir_path):
            print(f"Error! {dir_path} not found!")
            return None
        dir_ents = os.listdir(dir_path)
        for file in dir_ents:
            if file != "." and file != "..":
                file_list.append(dir_path + file)
        return file_list

    def poly_compile(self, bitcode_path: str, output_path: str, libs: List[str]) -> bool:
        """
        This function builds the compile command to instrument the whole program bitcode
        """
        compile_command = []
        source_dir = self.meta.compiler_dir + "../lib/libTaintSources.a"
        rt_dir = self.meta.compiler_dir + "../lib/libdfsan_rt-x86_64.a"
        if self.meta.is_cxx:
            compile_command.append("clang++")
        else:
            compile_command.append("clang")
        compile_command.append("-pie -fPIC")
        optimize = os.getenv("POLYCLANG_OPTIMIZE")
        if optimize is not None:
            compile_command.append("-O3")
        # -lpthread -Wl,--whole-archive libdfsan_rt-x86_64.a -Wl,--no-whole-archive libTaintSources.a -ldl -lrt -lstdc++
        compile_command.append("-g -o " + output_path + " " + bitcode_path)
        compile_command.append("-lpthread")
        compile_command.append("-Wl,--whole-archive")
        compile_command.append(rt_dir)
        compile_command.append("-Wl,--no-whole-archive")
        compile_command.append(source_dir)
        compile_command.append("-ldl -lrt")
        # if not self.meta.is_cxx:
        compile_command.append("-lstdc++")
        for lib in libs:
            compile_command.append(lib)
        command = " ".join(compile_command)
        print(command)
        ret_code = os.system(command)
        if ret_code != 0:
            print(f"Error! Failed to execute compile command: {compile_command}")
            return False
        return True

    def poly_opt(self, input_file: str, bitcode_file: str) -> bool:
        opt_command = ["opt -O0 -load", self.meta.compiler_dir + "../pass/libDataFlowSanitizerPass.so"]
        ignore_list_files: Optional[List[str]] = self.poly_add_inst_lists("ignore_lists")
        if ignore_list_files is None:
            print("Error! Failed to add ignore lists")
            return False
        track_list_files: Optional[List[str]] = self.poly_add_inst_lists("track_lists")
        if track_list_files is None:
            print("Error! Failed to add track_lists")
            return False
        for file in ignore_list_files:
            opt_command.append("-polytrack-dfsan-abilist=" + file)
        for file in track_list_files:
            opt_command.append("-polytrack-dfsan-abilist=" + file)
        opt_command.append(input_file)
        opt_command.append("-o")
        opt_command.append(bitcode_file)
        print(" ".join(opt_command))
        ret_code = os.system(" ".join(opt_command))
        if ret_code != 0:
            print("Error! opt command failed!")
            return False
        if not os.path.exists(bitcode_file):
            print("Error! Bitcode file does not exist!")
            return False
        return True

    def poly_instrument(self, input_file, output_file, bitcode_file, libs) -> bool:
        res = self.poly_opt(input_file, bitcode_file)
        if not res:
            print(f"Error instrumenting bitcode {input_file} with opt!")
            return False
        res = self.poly_compile(bitcode_file, output_file, libs)
        if not res:
            print(f"Error compiling bitcode!")
            return False
        return True

    def poly_build(self, argv) -> bool:
        compile_command = []
        if self.meta.is_cxx:
            compile_command.append("gclang++")
        else:
            compile_command.append("gclang")
        compile_command.append("-pie -fPIC")
        if self.meta.is_cxx:
            compile_command.append("-stdlib=libc++")
            compile_command.append("-nostdinc++")
            compile_command.append("-I" + self.meta.compiler_dir + "/../cxx_libs/include/c++/v1/")
            compile_command.append("-L" + self.meta.compiler_dir + "/../cxx_libs/lib/")
        for arg in argv[1:]:
            compile_command.append(arg)
        is_linking = self.poly_is_linking(argv)
        if is_linking:
            # If its cxx, link in our c++ libs
            if self.meta.is_cxx:
                compile_command.append("-lc++ -lc++abipoly -lc++abi")
            # Else, we still need stdc++ for our runtime
            else:
                compile_command.append("-lstdc++")
            compile_command.append("-lpthread")
            # compile_command.append("-lpthread -ldl -lrt -lm")
        print(" ".join(compile_command))
        res = os.system(" ".join(compile_command))
        if res != 0:
            return False
        return True


def main():
    parser = argparse.ArgumentParser(
        description="""
    Compiler wrapper around gllvm and instrumentation driver for PolyTracker

    Compile normally by invoking polybuild <whatever your arguments are> 
    These arguments will get passed to gclang/gclang++

    Extract the bitcode from the built target
    get-bc -b <target_binary> 

    OPTIONAL: Link multiple bitcode files together with llvm-link

    Instrument that whole program bitcode file by invoking 
    polybuild --instrument -f <bitcode_file.bc> -o <output_file> 
    """
    )
    parser.add_argument("--instrument", action="store_true", help="Specify to add polytracker instrumentation")
    parser.add_argument("--input-file", "-f", type=str, default=None, help="Path to the whole program bitcode file")
    parser.add_argument(
        "--output-bitcode-file",
        "-b",
        type=str,
        default="/tmp/temp_bitcode.bc",
        help="Outputs the bitcode file produced by opt, useful for debugging",
    )
    parser.add_argument("--output-file", "-o", type=str, default=None, help="Specify binary output path")
    parser.add_argument(
        "--target-instrument", action="store_true", help="Specify to build a single source file " "with instrumentation"
    )
    parser.add_argument(
        "--libs",
        nargs="+",
        default=[],
        help="Specify libraries to link with the instrumented target" "--libs -llib1 -llib2 -llib3 etc",
    )

    poly_build = PolyBuilder("++" in sys.argv[0])
    if sys.argv[1] == "--instrument":
        args = parser.parse_args(sys.argv[1:])
        # Do polyOpt/Compile
        if args.instrument:
            if args.output_file is None:
                print("Error! Outfile not specified, please specify with -o")
                sys.exit(1)
            if args.input_file is None:
                print("Error! Input file not specified, please specify with -f")
                sys.exit(1)
            if not os.path.exists(args.input_file):
                print("Error! Input file could not be found!")
                sys.exit(1)
            res = poly_build.poly_instrument(args.input_file, args.output_file, args.output_bitcode_file, args.libs)
            if not res:
                sys.exit(1)
        # do Build and opt/Compile for simple C/C++ program with no libs, just ease of use
    elif sys.argv[1] == "--target-instrument":
        # Find the output file
        output_file = ""
        for i, arg in enumerate(sys.argv):
            if arg == "-o":
                output_file = sys.argv[i + 1]
        if output_file == "":
            print("Error! Output file could not be found! Try specifying with -o")
            sys.exit(1)
        # Build the output file
        new_argv = [arg for arg in sys.argv if arg != "--target-instrument"]
        res = poly_build.poly_build(new_argv)
        if not res:
            print("Error! Building target failed!")
            sys.exit(1)
        os.system("get-bc -b " + output_file)
        input_bitcode_file = output_file + ".bc"
        res = poly_build.poly_instrument(input_bitcode_file, output_file, "/tmp/temp_bitcode.bc", [])
        if not res:
            print(f"Error! Failed to instrument bitcode {input_bitcode_file}")
            sys.exit(1)
    # Do gllvm build
    else:
        res = poly_build.poly_build(sys.argv)
        if not res:
            sys.exit(1)


if __name__ == "__main__":
    main()
