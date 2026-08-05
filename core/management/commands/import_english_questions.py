"""
One-off import of the IRN Republic Olympiad 2026 English test questions
(grades 1-11), transcribed from the PDFs supplied for the "МОСК английский
язык" subject. Correct answers were not marked reliably in the source PDFs,
so every question is imported with correct_option='' -- fill these in via
the admin Test Manager after import.

Usage:
    python manage.py import_english_questions --list
    python manage.py import_english_questions --sub-olympiad-id=<id> --dry-run
    python manage.py import_english_questions --sub-olympiad-id=<id>
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from core.models import SubOlympiad, SubOlympiadGrade, Test, Question


def _q(text, options):
    return {'text': text, 'options': options}


QUESTIONS_BY_GRADE = {
    1: [
        _q("There ___ a book on the table.", [('A', 'is'), ('B', 'are'), ('C', 'am'), ('D', 'be')]),
        _q("There ___ two cats in the room.", [('A', 'is'), ('B', 'are'), ('C', 'am'), ('D', 'be')]),
        _q("This is ___ bag.", [('A', 'my'), ('B', 'me'), ('C', 'I'), ('D', 'mine')]),
        _q("Is ____ your pen?", [('A', 'this'), ('B', 'these'), ('C', 'those'), ('D', 'they')]),
        _q("These ___ my books.", [('A', 'is'), ('B', 'are'), ('C', 'am'), ('D', 'be')]),
        _q("The cat is ___ the table.", [('A', 'on'), ('B', 'in'), ('C', 'under'), ('D', 'at')]),
        _q("I ___ swim.", [('A', 'can'), ('B', 'be'), ('C', 'is'), ('D', 'are')]),
        _q("He ___ fly.", [('A', 'can'), ('B', 'cans'), ('C', 'is'), ('D', 'are')]),
        _q("There ___ apples and two bananas.", [('A', 'is'), ('B', 'are'), ('C', 'am'), ('D', 'be')]),
        _q("Those ___ my shoes.", [('A', 'is'), ('B', 'be'), ('C', 'am'), ('D', 'are')]),
        _q("Word - Definition: Apple", [('A', 'A big animal'), ('B', 'A round fruit that can be red or green'), ('C', 'A place to live'), ('D', 'A toy')]),
        _q("Word - Definition: Umbrella", [('A', 'It helps in the rain'), ('B', 'It gives light'), ('C', 'You eat from it'), ('D', 'A farm animal')]),
        _q('Definition - Word: A small animal that says "meow."', [('A', 'Dog'), ('B', 'Bird'), ('C', 'Goat'), ('D', 'Cat')]),
        _q("Definition - Word: You write with it.", [('A', 'Book'), ('B', 'Table'), ('C', 'Pen'), ('D', 'Chair')]),
        _q("Find the synonym: Big", [('A', 'Small'), ('B', 'Large'), ('C', 'Short'), ('D', 'Cold')]),
        _q("Find the synonym: Fast", [('A', 'Slow'), ('B', 'Quick'), ('C', 'Heavy'), ('D', 'Late')]),
        _q("Find the synonym: Happy", [('A', 'Sad'), ('B', 'Angry'), ('C', 'Glad'), ('D', 'Dirty')]),
        _q("Find the antonym: Hot", [('A', 'Warm'), ('B', 'Cold'), ('C', 'Big'), ('D', 'Light')]),
        _q("Find the antonym: Clean", [('A', 'Dirty'), ('B', 'Happy'), ('C', 'Fast'), ('D', 'New')]),
        _q("Find the antonym: Old", [('A', 'Young'), ('B', 'Tall'), ('C', 'Full'), ('D', 'Early')]),
    ],
    2: [
        _q("There _____ a big cake on the table.", [('A', 'is'), ('B', 'are'), ('C', 'am'), ('D', 'be')]),
        _q("There _____ any milk in the fridge.", [('A', 'be'), ('B', "isn't"), ('C', 'are'), ('D', "aren't")]),
        _q("_____ there any apples in the basket? – Yes, _____.", [('A', 'Is / there is'), ('B', 'Are / there are'), ('C', 'Is / it is'), ('D', 'Are / they are')]),
        _q("I have _____ oranges. Do you want one?", [('A', 'a lot of'), ('B', 'a'), ('C', 'much'), ('D', 'any')]),
        _q("We don't have _____ sugar. Please buy some.", [('A', 'some'), ('B', 'a'), ('C', 'any'), ('D', 'a lot of')]),
        _q("_____ you like ice cream? – Yes, I _____.", [('A', 'Does / do'), ('B', 'Is / is'), ('C', 'Are / am'), ('D', 'Do / do')]),
        _q("My friends and I _____ to the park every Saturday.", [('A', 'going'), ('B', 'goes'), ('C', 'go'), ('D', 'am going')]),
        _q("_____ they play football after school? – No, they _____.", [('A', "Do / don't"), ('B', "Does / doesn't"), ('C', "Are / aren't"), ('D', "Is / isn't")]),
        _q("Excuse me, how much _____ this toy? – It _____ ten dollars.", [('A', 'is / is'), ('B', 'are / are'), ('C', 'is / are'), ('D', 'are / is')]),
        _q("What time _____? – It's half past three.", [('A', 'is it'), ('B', 'it be'), ('C', 'are you'), ('D', 'do you')]),
        _q("A person who comes from Italy is called _____.", [('A', 'Italy'), ('B', 'Italian'), ('C', 'American'), ('D', 'Italyian')]),
        _q("A person who designs buildings and makes plans for houses is an _____.", [('A', 'pilot'), ('B', 'architect'), ('C', 'teacher'), ('D', 'artist')]),
        _q("What is the opposite of ancient?", [('A', 'Old'), ('B', 'Historic'), ('C', 'Modern'), ('D', 'Traditional')]),
        _q("Which word means almost the same as seldom?", [('A', 'Always'), ('B', 'Never'), ('C', 'Often'), ('D', 'Rarely')]),
        _q("If a glass is transparent, you can _____.", [('A', 'see through it'), ('B', 'not see through it'), ('C', 'hear through it'), ('D', 'not break it easily')]),
        _q("The day between Tuesday and Thursday is _____.", [('A', 'Monday'), ('B', 'Wednesday'), ('C', 'Friday'), ('D', 'Saturday')]),
        _q("A place where you can borrow books for free is a _____.", [('A', 'bookshop'), ('B', 'library'), ('C', 'museum'), ('D', 'school gym')]),
        _q('In a shop, the shop assistant says: "Can I help you?" You want to buy an apple. What do you say?', [('A', 'I like bananas.'), ('B', 'Yes, please. One apple.'), ('C', 'How are you?'), ('D', 'I am 5 years old.')]),
        _q("Which sentence is correct?", [('A', 'There is three pencils on the desk.'), ('B', 'There are three pencil on the desk.'), ('C', 'There are three pencils on the desk.'), ('D', 'There is three pencil on the desk.')]),
        _q('You are in a toy shop. You see a nice car. You ask: "_____?" The shop assistant says: "It\'s five dollars."', [('A', 'How many'), ('B', 'What time'), ('C', 'How much'), ('D', 'What color')]),
    ],
    3: [
        _q("She _____ to school by bus every morning, but today she _____ walking.", [('A', 'go / is'), ('B', 'goes / is'), ('C', 'going / are'), ('D', 'went / were')]),
        _q("_____ does your father go to work? – At 7:30.", [('A', 'What time'), ('B', 'How often'), ('C', 'How many'), ('D', 'Which')]),
        _q("The train arrives _____ 5 o'clock _____ the evening.", [('A', 'at/on'), ('B', 'on/at'), ('C', 'in/on'), ('D', 'at/in')]),
        _q("There is _____ milk in the fridge, but we don't have _____ eggs.", [('A', 'many / much'), ('B', 'some / many'), ('C', 'a few / a little'), ('D', 'little / much')]),
        _q("This is _____ problem I have ever solved.", [('A', 'the most difficult'), ('B', 'more difficult'), ('C', 'difficult'), ('D', 'most difficult')]),
        _q("_____ information do you need to complete the project?", [('A', 'How many'), ('B', 'How much'), ('C', 'How often'), ('D', 'How long')]),
        _q("My brother is _____ than his friend, but his friend runs _____.", [('A', 'taller / faster'), ('B', 'tall / fast'), ('C', 'more tall / more fast'), ('D', 'tallest / fastest')]),
        _q("We always have a picnic _____ Sundays, but last Sunday it rained.", [('A', 'in'), ('B', 'on'), ('C', 'at'), ('D', 'by')]),
        _q("_____ sugar is bad for a health.", [('A', 'Too many'), ('B', 'Several'), ('C', 'A few'), ('D', 'Too much')]),
        _q("_____ bag is this? – It's mine.", [('A', 'Who'), ('B', 'Whose'), ('C', 'Where'), ('D', 'What')]),
        _q("Definition - Word: A person who writes poems.", [('A', 'Actor'), ('B', 'Poet'), ('C', 'Artist'), ('D', 'Musician')]),
        _q("Definition - Word: A very large, tall animal with a long neck and spots.", [('A', 'Elephant'), ('B', 'Giraffe'), ('C', 'Panda'), ('D', 'Rhinoceros')]),
        _q("Word - Definition: Exhausted", [('A', 'Full of energy'), ('B', 'Fast'), ('C', 'Angry'), ('D', 'Very tired')]),
        _q("Word - Definition: Enormous", [('A', 'Very small'), ('B', 'Very tall'), ('C', 'Very big'), ('D', 'Very loud')]),
        _q("Find the synonym: Rapid", [('A', 'Slow'), ('B', 'Quick'), ('C', 'Careful'), ('D', 'Loud')]),
        _q("Find the synonym: Joyful", [('A', 'Sad'), ('B', 'Happy'), ('C', 'Angry'), ('D', 'Scared')]),
        _q("Find the antonym: Brave", [('A', 'Courageous'), ('B', 'Fearful'), ('C', 'Strong'), ('D', 'Quiet')]),
        _q("Find the antonym: Create", [('A', 'Make'), ('B', 'Build'), ('C', 'Destroy'), ('D', 'Draw')]),
        _q("A whale cannot breathe underwater _____ it is a mammal, not a fish.", [('A', 'because'), ('B', 'so'), ('C', 'but'), ('D', 'although')]),
        _q("I am happy _____ it is my birthday.", [('A', 'because'), ('B', 'so'), ('C', 'but'), ('D', 'although')]),
    ],
    4: [
        _q("My parents _____ born in 1985, but I _____ born in 2017.", [('A', 'was / were'), ('B', 'were / was'), ('C', 'is / am'), ('D', 'are / is')]),
        _q("The museum _____ closed yesterday, so we _____ go inside.", [('A', 'was / could'), ('B', 'were / can'), ('C', 'was / could not'), ('D', 'are / must')]),
        _q("_____ you at the railway station last Monday? – No, I _____. I was at home.", [('A', "Was / wasn't"), ('B', "Were / weren't"), ('C', "Were / wasn't"), ('D', "Was / weren't")]),
        _q("They _____ to the beach last holiday because the weather _____ sunny.", [('A', 'go / is'), ('B', 'went / were'), ('C', 'goes / was'), ('D', 'went / was')]),
        _q("What time _____ the bus to Oxford _____ yesterday afternoon?", [('A', 'do / leave'), ('B', 'does / leaves'), ('C', 'did / left'), ('D', 'did / leave')]),
        _q("She _____ buy a train ticket because she _____ her money at home.", [('A', "didn't / forgot"), ('B', "don't / forget"), ('C', "wasn't / forgotten"), ('D', "isn't / forgetting")]),
        _q("We _____ to visit the old castle next weekend. We _____ already booked the tickets.", [('A', 'are going / have'), ('B', 'go / had'), ('C', 'went / were'), ('D', 'is going / has')]),
        _q("_____ you _____ to play tennis this Sunday? – Yes, we _____.", [('A', 'Do / go / are'), ('B', 'Are / going / are'), ('C', 'Did / went / did'), ('D', 'Is / going / is')]),
        _q("This is _____ station in the whole country. It was built in 1890.", [('A', 'older'), ('B', 'oldest'), ('C', 'more old'), ('D', 'the oldest')]),
        _q("My sister _____ born in March, and my brothers _____ born in April.", [('A', 'were / was'), ('B', 'was / were'), ('C', 'is / are'), ('D', 'are / is')]),
        _q('A: "Let\'s go to the zoo this Sunday." B: "________________"', [('A', "You're welcome."), ('B', 'That sounds great!'), ('C', 'At the park.'), ('D', 'I went to school yesterday.')]),
        _q('A: "Why are you so sad?" B: "________________"', [('A', 'I lost my new pen.'), ('B', 'The weather is nice.'), ('C', 'I love ice cream.'), ('D', 'My school is great.')]),
        _q('A: "Would you like some tea?" B: "________________"', [('A', 'Yes, I am.'), ('B', "No, it's not."), ('C', 'Yes, please.'), ('D', "I don't have friends at school.")]),
        _q('A: "How often do you play football?" B: "________________"', [('A', 'At the park.'), ('B', 'With my friends.'), ('C', 'Twice a week.'), ('D', 'A football player.')]),
        _q('A: "I\'m sorry I broke your toy." B: "________________"', [('A', "Don't worry."), ('B', "You're welcome."), ('C', 'Thank you.'), ('D', 'Good idea.')]),
        _q("Read the text and choose the correct answer to fill blank (16): Last summer, my family and I (16) _____ on a trip to the seaside. We stayed in a small hotel near the beach. Every morning, we (17) _____ up early to watch the sunrise. The water was very clean and blue. I (18) _____ swimming every day. My little sister built sandcastles. In the evenings, we ate fish and fresh fruit. The weather (19) _____ perfect. We all had a wonderful time. I hope we can go (20) _____ next year.", [('A', 'go'), ('B', 'went'), ('C', 'goes'), ('D', 'going')]),
        _q("Same text, blank (17): ... Every morning, we (17) _____ up early to watch the sunrise ...", [('A', 'stands'), ('B', 'wakes'), ('C', 'woke'), ('D', 'waking')]),
        _q("Same text, blank (18): ... I (18) _____ swimming every day ...", [('A', 'go'), ('B', 'went'), ('C', 'goes'), ('D', 'going')]),
        _q("Same text, blank (19): ... The weather (19) _____ perfect ...", [('A', 'is'), ('B', 'were'), ('C', 'are'), ('D', 'was')]),
        _q("Same text, blank (20): ... I hope we can go (20) _____ next year.", [('A', 'again'), ('B', 'always'), ('C', 'never'), ('D', 'today')]),
    ],
    5: [
        _q("By the time we arrived at the cinema, the film _____ already _____.", [('A', 'has / started'), ('B', 'had / started'), ('C', 'was / starting'), ('D', 'did / start')]),
        _q("If she _____ harder, she would have passed the exam.", [('A', 'studied'), ('B', 'had studied'), ('C', 'has studied'), ('D', 'studies')]),
        _q("Neither my parents nor my sister _____ to the party last night.", [('A', 'came'), ('B', 'come'), ('C', 'comes'), ('D', 'have come')]),
        _q("I wish I _____ more time to travel around the world.", [('A', 'have'), ('B', 'had'), ('C', 'will have'), ('D', 'would have')]),
        _q("This time next week, we _____ on a beach in Spain.", [('A', 'will lie'), ('B', 'will be lying'), ('C', 'lie'), ('D', 'are lying')]),
        _q("The higher you climb, _____ you will see.", [('A', 'farther'), ('B', 'the farther'), ('C', 'the furthest'), ('D', 'further')]),
        _q("She has been playing the piano _____ she was six years old.", [('A', 'for'), ('B', 'when'), ('C', 'which'), ('D', 'since')]),
        _q("The teacher told us that light _____ faster than sound.", [('A', 'travels'), ('B', 'travelled'), ('C', 'is travelling'), ('D', 'has travelled')]),
        _q("She _____ the test and also helped her classmates.", [('A', 'passed'), ('B', 'did pass'), ('C', 'has passed'), ('D', 'was passing')]),
        _q("This movie is _____ than the one we watched last week.", [('A', 'interesting'), ('B', 'the more interesting'), ('C', 'more interesting'), ('D', 'as interesting')]),
        _q("This is a long, narrow piece of cloth that men wear around their neck, usually with a suit.", [('A', 'a belt'), ('B', 'a tie'), ('C', 'mittens'), ('D', 'a glove')]),
        _q("This is a large, powerful animal that lives in the ocean and has a very loud song. It breathes air through a hole on top of its head.", [('A', 'a shark'), ('B', 'a dolphin'), ('C', 'a whale'), ('D', 'an octopus')]),
        _q("This is a person who studies the stars, planets, and space without leaving Earth. They use telescopes to look at the sky.", [('A', 'an astronomer'), ('B', 'an astronaut'), ('C', 'a geographer'), ('D', 'a biologist')]),
        _q("This is a type of energy that comes from moving air. Windmills and turbines are used to make it.", [('A', 'solar power'), ('B', 'wind power'), ('C', 'hydro power'), ('D', 'nuclear power')]),
        _q("This is a feeling of being very worried or nervous about something that might happen in the future.", [('A', 'excitement'), ('B', 'anxiety'), ('C', 'boredom'), ('D', 'relief')]),
        _q("Read and fill blank (16): Throughout history, humans have been deeply (16) _____ by the mystery of flight. The first successful hot air balloon flight in 1783 was a (17) _____ achievement. Later, the Wright brothers made a (18) _____ breakthrough by creating the first powered aircraft. Their invention (19) _____ a new era of travel. Today, millions of people fly every day, and the (20) _____ to reach even greater heights continues.", [('A', 'afraid'), ('B', 'keen'), ('C', 'fascinated'), ('D', 'fond')]),
        _q("Same text, blank (17): ... The first successful hot air balloon flight in 1783 was a (17) _____ achievement ...", [('A', 'remarks'), ('B', 'remark'), ('C', 'remarkably'), ('D', 'remarkable')]),
        _q("Same text, blank (18): ... the Wright brothers made a (18) _____ breakthrough ...", [('A', 'revolution'), ('B', 'revolutionary'), ('C', 'revolutionize'), ('D', 'revolutionarily')]),
        _q("Same text, blank (19): ... Their invention (19) _____ a new era of travel ...", [('A', 'marked'), ('B', 'marking'), ('C', 'mark'), ('D', 'remarkable')]),
        _q("Same text, blank (20): ... the (20) _____ to reach even greater heights continues.", [('A', 'desire'), ('B', 'desiring'), ('C', 'desired'), ('D', 'desirable')]),
    ],
    6: [
        _q("When I came home yesterday, my mother _____ dinner.", [('A', 'cooked'), ('B', 'has cooked'), ('C', 'was cooking'), ('D', 'cooks')]),
        _q("If you _____ hard, you will pass the exam.", [('A', 'study'), ('B', 'studied'), ('C', 'will study'), ('D', 'have studied')]),
        _q("John _____ to the party last Saturday.", [('A', 'was invited'), ('B', 'were invited'), ('C', 'invited'), ('D', 'has invited')]),
        _q("I wish I _____ taller so I could reach the top shelf.", [('A', 'am'), ('B', 'were'), ('C', 'had'), ('D', 'have been')]),
        _q("This time tomorrow, we _____ across the Atlantic Ocean.", [('A', 'fly'), ('B', 'will flying'), ('C', 'will be flying'), ('D', 'have flown')]),
        _q("The more you practice, _____ you will become.", [('A', 'better'), ('B', 'the better'), ('C', 'the best'), ('D', 'best')]),
        _q("She has lived in London _____ she was a child.", [('A', 'for'), ('B', 'since'), ('C', 'from'), ('D', 'during')]),
        _q("My father told me that the Earth _____ around the Sun.", [('A', 'revolves'), ('B', 'revolved'), ('C', 'is revolving'), ('D', 'has revolved')]),
        _q("He _____ the race and also broke the record.", [('A', 'wins'), ('B', 'was winning'), ('C', 'has won'), ('D', 'won')]),
        _q("This book is _____ than the one I read last month.", [('A', 'interesting'), ('B', 'more interesting'), ('C', 'most interesting'), ('D', 'as interesting')]),
        _q("This is a scientist who digs the ground to find old things like bones, tools, and buildings from ancient times.", [('A', 'archaeologist'), ('B', 'geologist'), ('C', 'biologist'), ('D', 'astronomer')]),
        _q("This happens when water gets hot and turns into vapor or gas.", [('A', 'condensation'), ('B', 'precipitation'), ('C', 'evaporation'), ('D', 'freezing')]),
        _q('This is a word like "and", "but", or "because" that joins two sentences or ideas together.', [('A', 'noun'), ('B', 'verb'), ('C', 'adjective'), ('D', 'conjunction')]),
        _q("This is the type of energy that comes from the sun and is used to generate electricity.", [('A', 'wind power'), ('B', 'hydro power'), ('C', 'solar power'), ('D', 'nuclear power')]),
        _q("This is a piece of clothing worn on the hands, with separate parts for each finger.", [('A', 'mittens'), ('B', 'gloves'), ('C', 'scarf'), ('D', 'belt')]),
        _q("Read and fill blank (16): Last weekend, our class went on an (16) _____ to the natural history museum. The guide showed us an (17) _____ collection of dinosaur fossils and it was great. One skeleton was so (18) _____ that it touched the ceiling. We learned that these creatures (19) _____ the Earth millions of years ago. After the tour, we had a (20) _____ discussion about extinction and climate change, this discussion lasted nearly 2 hours.", [('A', 'excursion'), ('B', 'picnic'), ('C', 'concert'), ('D', 'meeting')]),
        _q("Same text, blank (17): ... The guide showed us an (17) _____ collection of dinosaur fossils ...", [('A', 'tiring'), ('B', 'common'), ('C', 'boring'), ('D', 'impressive')]),
        _q("Same text, blank (18): ... One skeleton was so (18) _____ that it touched the ceiling ...", [('A', 'fragile'), ('B', 'enormous'), ('C', 'narrow'), ('D', 'shallow')]),
        _q("Same text, blank (19): ... these creatures (19) _____ the Earth millions of years ago ...", [('A', 'flew'), ('B', 'swam'), ('C', 'roamed'), ('D', 'slept')]),
        _q("Same text, blank (20): ... we had a (20) _____ discussion about extinction and climate change ...", [('A', 'lively'), ('B', 'silent'), ('C', 'short'), ('D', 'dangerous')]),
    ],
    7: [
        _q("By the end of this year, she _____ as a teacher for twenty years.", [('A', 'will work'), ('B', 'will have worked'), ('C', 'works'), ('D', 'is working')]),
        _q("If I _____ you, I would apologize immediately.", [('A', 'am'), ('B', 'were'), ('C', 'be'), ('D', 'had been')]),
        _q("They ___ TV when the electricity suddenly went off.", [('A', 'were watching'), ('B', 'watched'), ('C', 'watch'), ('D', 'are watching')]),
        _q('The passive form of "They are building a new hospital" is:', [('A', 'A new hospital is building'), ('B', 'A new hospital is being built'), ('C', 'A new hospital was built'), ('D', 'A new hospital has been built')]),
        _q("If you had told me earlier, I _____ you.", [('A', 'will help'), ('B', 'would help'), ('C', 'would have helped'), ('D', 'helped')]),
        _q("The number of students in the class _____ increasing.", [('A', 'have'), ('B', 'has'), ('C', 'are'), ('D', 'is')]),
        _q("She _____ English for five years before she moved to London.", [('A', 'had studied'), ('B', 'has studied'), ('C', 'studied'), ('D', 'was studying')]),
        _q("Yesterday, I _____ my friend at the park.", [('A', 'meet'), ('B', 'am meeting'), ('C', 'met'), ('D', 'have met')]),
        _q("The number of people without jobs _____ significantly over the last decade.", [('A', 'have increased'), ('B', 'has increased'), ('C', 'increase'), ('D', 'are increasing')]),
        _q("By the time we get to the airport, the plane _____ already _____.", [('A', 'has / left'), ('B', 'will / leave'), ('C', 'will have / left'), ('D', 'is / leaving')]),
        _q("This is the process by which plants make their own food using sunlight, water, and carbon dioxide.", [('A', 'respiration'), ('B', 'germination'), ('C', 'evaporation'), ('D', 'photosynthesis')]),
        _q("This is a long period of time when there is little or no rain, causing a shortage of water.", [('A', 'flood'), ('B', 'drought'), ('C', 'hurricane'), ('D', 'avalanche')]),
        _q("metamorphosis", [('A', 'a complete change in form or structure'), ('B', 'a type of food'), ('C', 'a musical instrument'), ('D', 'a clothing style')]),
        _q("biodiversity", [('A', 'the variety of life in a particular habitat or ecosystem'), ('B', 'a scientific experiment'), ('C', 'a type of energy'), ('D', 'a political system')]),
        _q("This is an irrational fear of a specific object, situation, or activity, such as heights or spiders.", [('A', 'anxiety'), ('B', 'phobia'), ('C', 'stress'), ('D', 'depression')]),
        _q("Read and fill blank (16): Climate change is one of the most (16) _____ challenges facing humanity today. Scientists have warned that if we do not (17) _____ our carbon emissions, the consequences could be disastrous. Rising sea levels, extreme weather events, and loss of biodiversity are just a few of the (18) _____ that have already been observed. Governments around the world are being urged to (19) _____ action and invest in renewable energy sources. (20) _____, many people believe that individual efforts, such as reducing waste and planting trees, can also make a difference.", [('A', 'trivial'), ('B', 'pressing'), ('C', 'amusing'), ('D', 'distant')]),
        _q("Same text, blank (17): ... if we do not (17) _____ our carbon emissions ...", [('A', 'increase'), ('B', 'ignore'), ('C', 'reduce'), ('D', 'celebrate')]),
        _q("Same text, blank (18): ... are just a few of the (18) _____ that have already been observed ...", [('A', 'benefits'), ('B', 'efforts'), ('C', 'effects'), ('D', 'solutions')]),
        _q("Same text, blank (19): ... Governments around the world are being urged to (19) _____ action ...", [('A', 'take'), ('B', 'make'), ('C', 'do'), ('D', 'put')]),
        _q("Same text, blank (20): ... (20) _____, many people believe that individual efforts ... can also make a difference.", [('A', 'Moreover'), ('B', 'For instance'), ('C', 'Such as'), ('D', 'For example')]),
    ],
    8: [
        _q("By the time the rescue team arrived, the survivors _____ for more than 48 hours.", [('A', 'have waited'), ('B', 'waited'), ('C', 'was waiting'), ('D', 'had been waiting')]),
        _q("If only I _____ more attention to the instructions, I wouldn't have made such a mistake.", [('A', 'pay'), ('B', 'had paid'), ('C', 'have paid'), ('D', 'would pay')]),
        _q("She _____ in the garden when the thunderstorm suddenly broke out.", [('A', 'worked'), ('B', 'has worked'), ('C', 'was working'), ('D', 'had worked')]),
        _q('The passive form of "Someone has stolen my bicycle" is:', [('A', 'My bicycle has been stolen'), ('B', 'My bicycle is stolen'), ('C', 'My bicycle was being stolen'), ('D', 'My bicycle had been stolen')]),
        _q("If she _____ earlier, she wouldn't have missed the bus.", [('A', 'left'), ('B', 'had left'), ('C', 'has left'), ('D', 'would leave')]),
        _q("The number of endangered species _____ dramatically over the past two decades.", [('A', 'have increased'), ('B', 'has increased'), ('C', 'are increasing'), ('D', 'increase')]),
        _q("They _____ each other for ten years before they finally got married.", [('A', 'have known'), ('B', 'had known'), ('C', 'know'), ('D', 'were knowing')]),
        _q("I _____ my wallet while I was shopping yesterday.", [('A', 'lose'), ('B', 'am losing'), ('C', 'lost'), ('D', 'have lost')]),
        _q("Every student in the class _____ to complete the assignment by Friday.", [('A', 'need'), ('B', 'needs'), ('C', 'are needing'), ('D', 'have needed')]),
        _q("By the end of next month, they _____ construction of the new bridge.", [('A', 'will complete'), ('B', 'will have completed'), ('C', 'complete'), ('D', 'are completing')]),
        _q("This is the branch of biology that deals with the relationships between living organisms and their environment.", [('A', 'ecology'), ('B', 'geology'), ('C', 'astronomy'), ('D', 'psycholog')]),
        _q("This is a situation in which a person is forced to choose between two equally difficult or unpleasant options.", [('A', 'opportunity'), ('B', 'dilemma'), ('C', 'solution'), ('D', 'advantage')]),
        _q("altruism", [('A', "selfish concern for one's own welfare"), ('B', 'the belief that life is meaningless'), ('C', 'unselfish concern for the well-being of others'), ('D', 'a fear of being in public places')]),
        _q("sustainable", [('A', 'causing harm to the environment'), ('B', 'able to be maintained at a certain rate or level'), ('C', 'temporary and short-lived'), ('D', 'extremely expensive')]),
        _q("This is a prejudice or preference that prevents objective consideration of an issue.", [('A', 'fact'), ('B', 'evidence'), ('C', 'bias'), ('D', 'truth')]),
        _q("Read and fill blank (16): Despite significant technological advancements over the past few decades, global inequality remains one of the most (16) _____ issues of our time. While some nations, particularly in North America and Western Europe, enjoy unprecedented prosperity and access to cutting-edge innovations, billions of people in other parts of the world continue to struggle with the most basic necessities. Access to clean drinking water, reliable healthcare, quality education, and adequate nutrition – things that many take for granted – remain distant dreams for nearly half of the global population. Economists and social scientists have warned repeatedly that without a concerted international effort, the (17) _____ between the wealthy and the poor will continue to widen at an alarming rate. This growing disparity is not only a matter of economic injustice but also poses serious threats to global stability, security, and long-term sustainable development. Various (18) _____ have been proposed over the years to address this complex challenge. These include large-scale debt relief programs for the most impoverished nations, the establishment of fair trade agreements that benefit developing economies, and significant investment in primary education and healthcare infrastructure. Some experts have also called for the creation of a global fund that would redistribute resources from wealthier countries to those in greatest need. However, implementing any of these solutions is far from straightforward. Success requires not only financial resources but also genuine political will, transparent governance, and (19) _____ cooperation that transcends national borders and narrow self-interests. (20) _____, critics point out that many similar initiatives in the past have ultimately failed. The primary reasons for these failures often include widespread corruption, mismanagement of funds, lack of local ownership, and a general absence of accountability mechanisms. Without addressing these underlying structural problems, even the most well-intentioned efforts are likely to produce disappointing results.", [('A', 'trivial'), ('B', 'neglectful'), ('C', 'amusing'), ('D', 'pressing')]),
        _q("Same text, blank (17): ... the (17) _____ between the wealthy and the poor will continue to widen ...", [('A', 'divide'), ('B', 'uniformity'), ('C', 'harmony'), ('D', 'similarity')]),
        _q("Same text, blank (18): ... Various (18) _____ have been proposed over the years to address this complex challenge ...", [('A', 'problems'), ('B', 'symptoms'), ('C', 'remedies'), ('D', 'causes')]),
        _q("Same text, blank (19): ... genuine political will, transparent governance, and (19) _____ cooperation ...", [('A', 'local'), ('B', 'individual'), ('C', 'international'), ('D', 'temporary')]),
        _q("Same text, blank (20): ... (20) _____, critics point out that many similar initiatives in the past have ultimately failed.", [('A', 'Firstly'), ('B', 'For instance'), ('C', 'Secondly'), ('D', 'Indeed')]),
    ],
    9: [
        _q("By the time we _____ the cinema, the film _____ already started.", [('A', 'reached / had'), ('B', 'reach / has'), ('C', 'were reaching / was'), ('D', 'have reached / is')]),
        _q("She wishes she _____ harder when she was at university.", [('A', 'studies'), ('B', 'had studied'), ('C', 'has studied'), ('D', 'would study')]),
        _q("The old castle, which _____ in the 12th century, _____ millions of visitors every year.", [('A', 'built / attracts'), ('B', 'was built / attracts'), ('C', 'built / attracted'), ('D', 'was built / attracted')]),
        _q("If you _____ me about the meeting, I wouldn't have missed it.", [('A', 'told'), ('B', 'have told'), ('C', 'had told'), ('D', 'would tell')]),
        _q("This time next Friday, we _____ our final exams.", [('A', 'take'), ('B', 'will take'), ('C', 'will be taking'), ('D', 'have taken')]),
        _q("The number of people without access to clean water _____ significantly over the past decade.", [('A', 'have decreased'), ('B', 'has decreased'), ('C', 'decrease'), ('D', 'are decreasing')]),
        _q("He _____ in three different countries before he finally settled in Canada.", [('A', 'lived'), ('B', 'has lived'), ('C', 'had lived'), ('D', 'was living')]),
        _q("I _____ my keys while I was walking home yesterday.", [('A', 'lose'), ('B', 'am losing'), ('C', 'lost'), ('D', 'have lost')]),
        _q("It's high time you _____ smoking. It's bad for your health.", [('A', 'stop'), ('B', 'stopped'), ('C', 'have stopped'), ('D', 'will stop')]),
        _q("By the end of this year, they _____ the new school building.", [('A', 'will complete'), ('B', 'are completing'), ('C', 'complete'), ('D', 'will have completed')]),
        _q('Idiom: What does the idiom "to bite the bullet" mean?', [('A', 'to avoid a difficult situation'), ('B', 'to complain about something'), ('C', 'to give up easily'), ('D', 'to face a difficult situation bravely')]),
        _q('Idiom: What does the idiom "to cut corners" mean?', [('A', 'to do something carefully'), ('B', 'to finish something quickly and well'), ('C', 'to do something in the cheapest or easiest way'), ('D', 'to start a new project')]),
        _q('Idiom: What does the idiom "to hit the nail on the head" mean?', [('A', 'to describe exactly what is wrong'), ('B', 'to make a mistake'), ('C', 'to work very slowly'), ('D', 'to avoid answering a question')]),
        _q('Idiom: What does the idiom "to let the cat out of the bag" mean?', [('A', 'to hide a secret'), ('B', 'to accidentally reveal a secret'), ('C', 'to catch an animal'), ('D', 'to make a big mistake')]),
        _q('Idiom: What does the idiom "to be under the weather" mean?', [('A', 'to feel very happy'), ('B', 'to feel slightly ill or unwell'), ('C', 'to be very tired'), ('D', 'to be very angry')]),
        _q("Phrasal Verb: The meeting was _____ because the manager was sick.", [('A', 'called off'), ('B', 'put off'), ('C', 'taken off'), ('D', 'turned off')]),
        _q("Phrasal Verb: Can you _____ this word in the dictionary? I don't know what it means.", [('A', 'look for'), ('B', 'look after'), ('C', 'look up'), ('D', 'look into')]),
        _q("Word Formation: Her _____ to become a doctor made her study very hard.", [('A', 'decide'), ('B', 'decision'), ('C', 'decisive'), ('D', 'decidedly')]),
        _q("Confusing Words: His explanation was so _____ that nobody could understand it.", [('A', 'clear'), ('B', 'obvious'), ('C', 'simple'), ('D', 'vague')]),
        _q("Confusing Words: She gave me some useful _____ on how to prepare for the exam.", [('A', 'advise'), ('B', 'advices'), ('C', 'advice'), ('D', 'advising')]),
    ],
    10: [
        _q("She _____ English for five years before she moved to London.", [('A', 'has studied'), ('B', 'had studied'), ('C', 'studied'), ('D', 'was studying')]),
        _q("By the time you _____ back, I _____ all the work.", [('A', 'come / will have finished'), ('B', 'came / finished'), ('C', 'will come / finish'), ('D', 'come / finishing')]),
        _q("I wish I _____ more time to travel when I was young.", [('A', 'had'), ('B', 'have had'), ('C', 'had had'), ('D', 'will have')]),
        _q("The bridge, which _____ in 1980, _____ recently renovated.", [('A', 'built / was'), ('B', 'was built / has been'), ('C', 'was built / was'), ('D', 'built / has been')]),
        _q("If I _____ you, I _____ that job immediately.", [('A', 'were / would accept'), ('B', 'had been / would accept'), ('C', 'am / will accept'), ('D', 'was / accept')]),
        _q("Don't call me between 2 and 3 pm tomorrow. I _____ a lecture then.", [('A', 'give'), ('B', 'will give'), ('C', 'have given'), ('D', 'will be giving')]),
        _q("The use of smartphones in classrooms _____ becoming more common.", [('A', 'is'), ('B', 'are'), ('C', 'were'), ('D', 'have been')]),
        _q("This is the most beautiful painting I _____ ever _____.", [('A', 'have / seen'), ('B', 'had / seen'), ('C', 'am / seeing'), ('D', 'was / seen')]),
        _q("He suggested _____ to the cinema instead of staying at home.", [('A', 'to go'), ('B', 'go'), ('C', 'going'), ('D', 'went')]),
        _q("If she _____ harder, she would have passed the exam.", [('A', 'studied'), ('B', 'has studied'), ('C', 'would study'), ('D', 'had studied')]),
        _q('Idiom: What does the idiom "to burn the midnight oil" mean?', [('A', 'to sleep very late'), ('B', 'to work or study late into the night'), ('C', 'to start a fire'), ('D', 'to waste time')]),
        _q('Idiom: What does the idiom "to be in the same boat" mean?', [('A', 'to be on a boat together'), ('B', 'to travel together'), ('C', 'to be in the same difficult situation'), ('D', 'to agree with someone')]),
        _q('Idiom: What does the idiom "to play it by ear" mean?', [('A', 'to play music without notes'), ('B', 'to decide what to do as the situation develops'), ('C', 'to listen carefully'), ('D', 'to follow instructions strictly')]),
        _q('Idiom: What does the idiom "to give someone the cold shoulder" mean?', [('A', 'to ignore someone deliberately'), ('B', 'to be cold to someone'), ('C', 'to help someone'), ('D', 'to hug someone')]),
        _q('Idiom: What does the idiom "to get cold feet" mean?', [('A', 'to feel brave'), ('B', 'to feel nervous and hesitant'), ('C', 'to be very cold'), ('D', 'to run fast')]),
        _q("Phrasal Verb: The committee _____ the proposal because it was too expensive.", [('A', 'turned down'), ('B', 'turned up'), ('C', 'turned on'), ('D', 'turned over')]),
        _q("Phrasal Verb: We need to _____ the problem before it gets worse.", [('A', 'look after'), ('B', 'look for'), ('C', 'look into'), ('D', 'look over')]),
        _q("Word Formation: The _____ of the new policy was felt immediately.", [('A', 'effective'), ('B', 'effect'), ('C', 'effectively'), ('D', 'effectiveness')]),
        _q("Confusing Words: She _____ her hair every morning.", [('A', 'braids'), ('B', 'brays'), ('C', 'braves'), ('D', 'brakes')]),
        _q("Confusing Words: She is very _____ about her future career.", [('A', 'worrying'), ('B', 'sensibly'), ('C', 'sensitive'), ('D', 'sense')]),
    ],
    11: [
        _q("She _____ by the time we arrived.", [('A', 'had left'), ('B', 'has left'), ('C', 'was leaving'), ('D', 'left')]),
        _q("If he _____ earlier, he wouldn't have missed the train.", [('A', 'would leave'), ('B', 'has left'), ('C', 'had left'), ('D', 'left')]),
        _q("By next year, they _____ the project.", [('A', 'will complete'), ('B', 'are completing'), ('C', 'complete'), ('D', 'will have completed')]),
        _q("I'd rather you _____ me the truth yesterday.", [('A', 'told'), ('B', 'have told'), ('C', 'had told'), ('D', 'tell')]),
        _q("The book _____ by the time I returned to the library.", [('A', 'was borrowed'), ('B', 'borrowed'), ('C', 'has borrowed'), ('D', 'had been borrowed')]),
        _q("Hardly _____ the room when the phone rang.", [('A', 'did I left'), ('B', 'had I left'), ('C', 'I left'), ('D', 'I had left')]),
        _q("Ten minutes _____ enough to finish the test.", [('A', 'are'), ('B', 'have'), ('C', 'is'), ('D', 'were')]),
        _q("She is used to _____ early in the morning.", [('A', 'woke'), ('B', 'be waking'), ('C', 'waking'), ('D', 'wake')]),
        _q("I wish I _____ how to solve this problem.", [('A', 'knew'), ('B', 'know'), ('C', 'would know'), ('D', 'have known')]),
        _q("He denied _____ the money.", [('A', 'to steal'), ('B', 'stealing'), ('C', 'stole'), ('D', 'steal')]),
        _q('Idiom: "Break the ice" means:', [('A', 'start a conversation'), ('B', 'destroy something'), ('C', 'feel cold'), ('D', 'end a relationship')]),
        _q('Idiom: "Hit the nail on the head" means:', [('A', 'make a mistake'), ('B', 'work hard'), ('C', 'hit something hard'), ('D', 'be exactly right')]),
        _q('Idiom: "Cost an arm and a leg" means:', [('A', 'be dangerous'), ('B', 'be painful'), ('C', 'be expensive'), ('D', 'be cheap')]),
        _q('Idiom: "Once in a blue moon" means:', [('A', 'always'), ('B', 'very rarely'), ('C', 'sometimes'), ('D', 'very often')]),
        _q('Idiom: "Spill the beans" means:', [('A', 'waste money'), ('B', 'make a mess'), ('C', 'cook food'), ('D', 'reveal a secret')]),
        _q("Phrasal Verb: She _____ an interesting idea during the meeting.", [('A', 'came into'), ('B', 'came over'), ('C', 'came up with'), ('D', 'came across')]),
        _q("Phrasal Verb: We must _____ this issue immediately.", [('A', 'deal in'), ('B', 'deal with'), ('C', 'deal up'), ('D', 'deal off')]),
        _q("Word Formation: His _____ helped him succeed in business.", [('A', 'determined'), ('B', 'determinately'), ('C', 'determine'), ('D', 'determination')]),
        _q("Confusing Words: He _____ a compliment to his teacher.", [('A', 'said'), ('B', 'laid'), ('C', 'payed'), ('D', 'paid')]),
        _q("Confusing Words: She is very _____ to criticism.", [('A', 'sensible'), ('B', 'sensibly'), ('C', 'sensitive'), ('D', 'sense')]),
    ],
}


class Command(BaseCommand):
    help = (
        "One-off import of the IRN Republic Olympiad 2026 English test questions "
        "(grades 1-11) for a given SubOlympiad. Correct answers are left blank -- "
        "fill them in via the admin Test Manager after import."
    )

    def add_arguments(self, parser):
        parser.add_argument('--sub-olympiad-id', type=int, default=None,
                             help='SubOlympiad id to import into (e.g. the "МОСК английский язык" subject).')
        parser.add_argument('--list', action='store_true',
                             help='List candidate SubOlympiads (title containing english-like keywords) and exit.')
        parser.add_argument('--overwrite', action='store_true',
                             help="Delete a grade's existing questions before importing (default: skip grades that already have questions).")
        parser.add_argument('--dry-run', action='store_true',
                             help='Preview what would be created without writing to the database.')

    def handle(self, *args, **options):
        if options['list']:
            subs = SubOlympiad.objects.filter(
                Q(title_ru__icontains='англ') | Q(title_en__icontains='english') | Q(title_uz__icontains='ingliz')
            ).select_related('olympiad')
            if not subs:
                self.stdout.write('No matching SubOlympiad found.')
                return
            for s in subs:
                self.stdout.write(f"id={s.id}  \"{s.title_ru or s.title_en or s.title_uz}\"  (olympiad: {s.olympiad.title_ru}, id={s.olympiad_id})")
            return

        sub_id = options.get('sub_olympiad_id')
        if not sub_id:
            raise CommandError('Pass --sub-olympiad-id=<id> (use --list to find it first).')

        try:
            sub = SubOlympiad.objects.get(id=sub_id)
        except SubOlympiad.DoesNotExist:
            raise CommandError(f'No SubOlympiad with id={sub_id}')

        dry = options['dry_run']
        overwrite = options['overwrite']

        for grade, questions in QUESTIONS_BY_GRADE.items():
            try:
                gs = SubOlympiadGrade.objects.get(sub_olympiad=sub, grade=str(grade))
            except SubOlympiadGrade.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Grade {grade}: no SubOlympiadGrade session found for this subject, skipping.'))
                continue

            try:
                test = gs.test
            except Test.DoesNotExist:
                test = None

            if test and test.questions.exists():
                if not overwrite:
                    self.stdout.write(self.style.WARNING(
                        f'Grade {grade}: test already has {test.questions.count()} questions, skipping (pass --overwrite to replace).'
                    ))
                    continue
                if not dry:
                    test.questions.all().delete()

            if dry:
                verb = 'replace' if (test and overwrite) else 'create'
                self.stdout.write(f'Grade {grade}: would {verb} test and import {len(questions)} questions.')
                continue

            if not test:
                test = Test.objects.create(sub_olympiad_grade=gs, title=f"{sub.title_ru or sub.title_en} ({grade} кл.)")

            objs = [
                Question(
                    test=test,
                    text_ru=q['text'], text_uz=q['text'], text_en=q['text'],
                    options=[{'id': opt_id, 'text': opt_text} for opt_id, opt_text in q['options']],
                    correct_option='',
                )
                for q in questions
            ]
            Question.objects.bulk_create(objs)
            self.stdout.write(self.style.SUCCESS(f'Grade {grade}: imported {len(objs)} questions (test id={test.id}).'))
