# Sample Buggy Python Code for Testing the Debugger
# Copy and paste these examples into the web interface

# Example 1: Missing function argument
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)

numbers = [1, 2, 3, 4, 5]
result = calculate_average()  # BUG: Missing argument
print(f"Average: {result}")

# Example 2: Variable not defined
def greet_user():
    print(f"Hello, {username}!")  # BUG: username not defined

greet_user()

# Example 3: Index out of range
my_list = [1, 2, 3]
print(my_list[5])  # BUG: Index 5 doesn't exist

# Example 4: Division by zero
def divide_numbers(a, b):
    return a / b

result = divide_numbers(10, 0)  # BUG: Division by zero
print(result)

# Example 5: Type error
def add_numbers(a, b):
    return a + b

result = add_numbers("hello", 5)  # BUG: Can't add string and integer
print(result)

# Example 6: Import error
import non_existent_module  # BUG: Module doesn't exist

# Example 7: Syntax error (uncomment to test)
# def broken_function(
#     print("Missing closing parenthesis")

# Example 8: Indentation error (uncomment to test)
# def another_function():
# print("Wrong indentation")  # BUG: Should be indented

# Common Error Messages to use with the examples above:
"""
1. TypeError: calculate_average() missing 1 required positional argument: 'numbers'
2. NameError: name 'username' is not defined
3. IndexError: list index out of range
4. ZeroDivisionError: division by zero
5. TypeError: can only concatenate str (not "int") to str
6. ModuleNotFoundError: No module named 'non_existent_module'
7. SyntaxError: unexpected EOF while parsing
8. IndentationError: expected an indented block
""" 