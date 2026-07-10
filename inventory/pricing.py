def calculate_price(base_price, condition_score):
    multiplier = 0.3 + (condition_score - 1) / 9 * 0.7
    return round(base_price * multiplier, 2)


if __name__ == "__main__":
    print(calculate_price(12000, 8))   # realistic PKR base price
    print(calculate_price(12000, 10))  # should print 12000.0
    print(calculate_price(12000, 1))   # should print 3600.0