"""names: name tables for generated residents."""
U = world.require('util')

MALE = ['James', 'Michael', 'Robert', 'David', 'Daniel', 'Paul', 'Mark', 'George', 'Kevin', 'Brian', 'Edward',
        'Jason', 'Ryan', 'Gary', 'Eric', 'Stephen', 'Larry', 'Scott', 'Frank', 'Raymond', 'Patrick', 'Jack',
        'Dennis', 'Jerry', 'Tyler', 'Aaron', 'Henry', 'Adam', 'Nathan', 'Peter', 'Kyle', 'Walter', 'Harold',
        'Carl', 'Arthur', 'Roger', 'Joe', 'Albert', 'Terry', 'Sean', 'Minh', 'Jin', 'Hiro', 'Tuan', 'Wei',
        'Luis', 'Marco', 'Andre', 'Darnell', 'Malik', 'Omar', 'Viktor', 'Pavel', 'Stan', 'Leo', 'Ben', 'Sam',
        'Max', 'Owen', 'Caleb']
FEMALE = ['Mary', 'Patricia', 'Linda', 'Barbara', 'Susan', 'Jessica', 'Sarah', 'Karen', 'Nancy', 'Lisa',
          'Margaret', 'Sandra', 'Ashley', 'Kimberly', 'Donna', 'Emily', 'Carol', 'Michelle', 'Amanda', 'Melissa',
          'Deborah', 'Stephanie', 'Rebecca', 'Laura', 'Helen', 'Sharon', 'Cynthia', 'Kathleen', 'Amy', 'Angela',
          'Anna', 'Brenda', 'Pamela', 'Nicole', 'Ruth', 'Katherine', 'Samantha', 'Christine', 'Catherine',
          'Rachel', 'Mai', 'Yuki', 'Linh', 'Mei', 'Hana', 'Rosa', 'Carmen', 'Aaliyah', 'Imani', 'Fatima', 'Olga',
          'Irina', 'Greta', 'Nora', 'Ivy', 'Tess', 'June', 'Ada', 'Zoe', 'Paige']
LAST = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Miller', 'Davis', 'Wilson', 'Anderson', 'Taylor',
        'Thomas', 'Moore', 'Martin', 'Jackson', 'Thompson', 'White', 'Harris', 'Clark', 'Lewis', 'Robinson',
        'Walker', 'Young', 'Allen', 'King', 'Wright', 'Scott', 'Hill', 'Green', 'Adams', 'Nelson', 'Baker',
        'Hall', 'Campbell', 'Mitchell', 'Carter', 'Roberts', 'Phillips', 'Evans', 'Turner', 'Parker', 'Collins',
        'Edwards', 'Stewart', 'Morris', 'Murphy', 'Cook', 'Rogers', 'Morgan', 'Cooper', 'Peterson', 'Reed',
        'Bailey', 'Bell', 'Kelly', 'Howard', 'Ward', 'Cox', 'Richardson', 'Wood', 'Watson', 'Brooks', 'Bennett',
        'Gray', 'Hughes', 'Price', 'Sanders', 'Myers', 'Long', 'Ross', 'Foster', 'Nguyen', 'Tran', 'Kim', 'Park',
        'Chen', 'Tanaka', 'Sato', 'Lee', 'Garcia', 'Lopez', 'Rossi', 'Novak', 'Kowalski', 'Schmidt', 'Weber',
        'Okafor', 'Haddad', 'Petrov', 'Doyle', 'Flynn']

used = set()


def person(sex=None):
    """Returns (name, sex); names are unique within a running world."""
    sex = sex or U.pick('mf')
    for attempt in range(50):
        name = f"{U.pick(MALE if sex == 'm' else FEMALE)} {U.pick(LAST)}"
        if name not in used:
            break
    used.add(name)
    return name, sex
