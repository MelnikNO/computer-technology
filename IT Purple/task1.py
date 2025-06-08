# TASK 1
def almost_palindrome(s):
    def palindrome(text):
        return text == text[::-1]

    for i in range(len(s)):
        temp = s[:i] + s[i + 1:]
        if palindrome(temp):
            return "YES"

    return "NO"

s = input("Write a 4-letter word: ")

print(almost_palindrome(s))


# TASK 2
def find_next_train(a, b, d):
    if d <= a:
        return a
    else:
        k = (d - a + b - 1) // b
        return a + k * b

def solve():
    n = int(input("Введите количество веток метро (n) от 1 до 100 включительно: "))

    if not (1 <= n <= 100):
        return "Ошибка: Число должно быть от 0 до 100"

    print("Введите расписание для каждой ветки (a b) (*каждая на новой строке*):")
    schedule = []
    for x in range(n):
        print(f"Введите расписание для ветки {x + 1} (через пробел и потом переход на новую строку): ")
        a, b = map(int, input().split())

        if not (0 <= a < b <= 10**9):
            return "Ошибка: Число должно быть от 0 до 10**9 и a < b"

        schedule.append([a, b])

    q = int(input("Введите количество запросов (q): "))

    if not (1 <= q <= 100):
        return "Ошибка: Число должно быть от 0 до 100"

    print("Введите запросы (t d) (*каждый на новой строке*):")
    for x in range(q):
        print(f"Введите запрос {x + 1} (через пробел и потом переход на новую строку): ")
        t, d = map(int, input().split())

        if not (1 <= t <= n and 1 <= d <= 10 ** 9):
            return "Ошибка: Число d должно быть от 1 до 10**9 и t < n"

        a, b = schedule[t - 1]
        print(find_next_train(a, b, d))

solve()


# TASK 3
def solve():
    n = int(input("Введите длину массива (от 1 до 2 * 10^5 включительно): "))
    a = list(map(int, input("Введите массив целых чисел a длины n (1 <= a <= 10^9): ").split()))

    if not (1 <= n <= 2 * 10**5):
        return "Ошибка: Число должно быть от 1 до 2 * 10**5"

    if len(a) != n:
        return "Ошибка: Длина введенного массива не соответствует указанной длине"

    for num in a:
        if not (1 <= num <= 10**9):
            return "Ошибка: Все элементы массива должны быть от 1 до 10^9"

    unique_numbers = set()
    count = 0

    for num in a:
        current_num = num
        while current_num > 0:
            if current_num not in unique_numbers:
                unique_numbers.add(current_num)
                count += 1
                break
            else:
                current_num //= 2

    print(count)

solve()


# TASK 4
def solve():
    n = int(input("Введите длину массива (от 3 до 10^5 включительно): "))
    a = list(map(int, input("Введите элементы массива (от 1 до 10 включительно): ").split()))

    if not (3 <= n <= 10 ** 5):
        return "Ошибка: Число должно быть от 3 до 10**5"

    if len(a) != n:
        return "Ошибка: Длина введенного массива не соответствует указанной длине"

    for num in a:
        if not (1 <= num <= 10):
            return "Ошибка: Все элементы массива должны быть от 1 до 10"

    count = 0

    for i in range(n - 2):
        for j in range(i + 2, n):
            arithm_progression = False
            for k in range(j - i - 1):
                for l in range(k + 1, j - i):
                    for m in range(l + 1, j - i + 1):
                        if a[i+l] - a[i+k] == a[i+m] - a[i+l]:
                            arithm_progression = True
                            break
                    if arithm_progression:
                        break
                if arithm_progression:
                    break

            if arithm_progression:
                count += 1

    print(count)

solve()


# TASK 5
def is_valid(s):
    balance = 0
    for char in s:
        if char == '(':
            balance += 1
        elif char == ')':
            balance -= 1
        if balance < 0:
            return False
    return balance == 0


def solve():
    print("Введите n, a, b (три числа через пробел), n должно быть от 1 до 5 * 10^5 включительно, a и b - от 1 до 10^9 включительно: ")
    n, a, b = map(int, input().split())

    if not (1 <= n <= 5 * 10 ** 5 and 1 <= a <= 10 ** 9 and 1 <= b <= 10 ** 9):
        return "Ошибка: n должно быть от 1 до 5 * 10^5, a и b - от 1 до 10^9"

    print("Введите строку из '(' и ')' длиной 2n: ")
    s = list(input())

    if len(s) != 2 * n:
        return "Ошибка: длина строки должна быть 2n"

    for char in s:
        if char != '(' and char != ')':
            return "Ошибка: Строка должна содержать только символы '(' и ')'"

    cost = 0

    while not is_valid(s):

        balance = 0
        need_change_index = -1
        for i in range(2 * n):
            if s[i] == '(':
                balance += 1
            else:
                balance -= 1

            if balance < 0:
                need_change_index = i
                break

        if need_change_index != -1:
            found_swap = False
            for j in range(need_change_index + 1, 2 * n):
                if s[j] == '(':
                    s[need_change_index], s[j] = s[j], s[need_change_index]
                    cost += a
                    found_swap = True
                    break

            if not found_swap:
                s[need_change_index] = '('
                cost += b
        else:

            balance = 0
            need_change_index = -1
            for i in range(2 * n - 1, -1, -1):
                if s[i] == ')':
                    balance += 1
                else:
                    balance -= 1

                if balance < 0:
                    need_change_index = i
                    break
            if need_change_index != -1:
                s[need_change_index] = ')'
                cost += b

    print(cost)

solve()


# TASK 6
def solve():
    n = int(input("Введите количество сотрудников (n) от 2 до 3 * 10^5: "))

    if not (2 <= n <= 3 * 10**5):
        print("Ошибка: Количество сотрудников должно быть между 2 и 3 * 10^5.")
        return

    a = list(map(int, input("Введите росты сотрудников (a1 a2 ... an), разделенные пробелами: ").split()))

    if len(a) != n:
        print("Ошибка: Количество ростов не соответствует количеству сотрудников.")
        return

    for height in a:
        if not (1 <= height <= 10**9):
            print("Ошибка: Рост сотрудника должен быть между 1 и 10^9.")
            return

    a.sort()

    total_diff = 0
    left = 0
    right = n - 1

    while left < right:
        total_diff += abs(a[left] - a[right])
        left += 1
        right -= 1

    print(total_diff)

solve()


# TASK 7
def gcd(a, b):
    if b == 0:
        return a
    return gcd(b, a % b)


def solve():
    n = int(input("Введите количество чисел в последовательности (n) от 2 до 1000 включительно: "))

    if not (2 <= n <= 1000):
        print("Ошибка: Количество чисел должно быть между 2 и 1000.")
        return

    a = list(map(int, input("Введите массив a (a1 a2 ... an-1), разделенные пробелами от 1 до 1000 включительно: ").split()))

    if len(a) != n - 1:
        print("Ошибка: Количество чисел в массиве a должно быть n-1.")
        return

    for val in a:
        if not (1 <= val <= 1000):
            print("Ошибка: Значение в массиве a должно быть между 1 и 1000.")
            return

    MOD = 998244353

    def get_coprime_pair(x):
        factors = []
        for i in range(1, x + 1):
            if x % i == 0:
                factors.append((i, x // i))

        coprime_pairs = []
        for p, q in factors:
            if gcd(p, q) == 1:
                coprime_pairs.append((p, q))
        return coprime_pairs

    def calculate_interest(b):
        interest = 1
        for num in b:
            interest = (interest * num) % MOD
        return interest

    def find_beautiful_sequences(index, current_sequence):
        if index == n:
            current_gcd = current_sequence[0]
            for i in range(1, len(current_sequence)):  # Исправлено
                current_gcd = gcd(current_gcd, current_sequence[i])

            if current_gcd == 1:
                return calculate_interest(current_sequence)
            else:
                return 0

        total_interest = 0

        if index > len(a):
            return 0

        p, q = current_sequence[-1], a[index - 1]
        possible_next_nums = []

        if (a[index - 1] % current_sequence[-1] == 0):
            next_num = a[index - 1] // current_sequence[-1]
            if (gcd(current_sequence[-1], next_num) == 1):
                possible_next_nums = [next_num]
        else:
            coprime_pairs = get_coprime_pair(a[index - 1])
            for p1, q1 in coprime_pairs:
                if (gcd(p1, current_sequence[-1]) == 1) or (gcd(q1, current_sequence[-1]) == 1):
                    if current_sequence[-1] == p1:
                        possible_next_nums = [q1]
                    elif current_sequence[-1] == q1:
                        possible_next_nums = [p1]

        for next_num in possible_next_nums:
            new_sequence = current_sequence + [next_num]
            total_interest = (total_interest + find_beautiful_sequences(index + 1, new_sequence)) % MOD

        return total_interest

    total_sum_of_interests = 0

    first_coprime_pairs = get_coprime_pair(a[0])

    for p1, q1 in first_coprime_pairs:
        total_sum_of_interests = (total_sum_of_interests + find_beautiful_sequences(2, [p1])) % MOD

        total_sum_of_interests = (total_sum_of_interests + find_beautiful_sequences(2, [q1])) % MOD
    print("Сумма интересностей:", total_sum_of_interests)


solve()