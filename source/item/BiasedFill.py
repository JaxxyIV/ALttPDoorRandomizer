import RaceRandom as random
import logging
from math import ceil
from collections import defaultdict

from DoorShuffle import validate_vanilla_reservation
from Dungeons import dungeon_table
from Items import item_table, ItemFactory


class ItemPoolConfig(object):

    def __init__(self):
        self.location_groups = None
        self.static_placement = None
        self.item_pool = None
        self.placeholders = None
        self.reserved_locations = defaultdict(set)


class LocationGroup(object):
    def __init__(self, name):
        self.name = name
        self.locations = []

        # flags
        self.keyshuffle = False
        self.keydropshuffle = False
        self.shopsanity = False
        self.retro = False

    def locs(self, locs):
        self.locations = list(locs)
        return self

    def flags(self, k, d=False, s=False, r=False):
        self.keyshuffle = k
        self.keydropshuffle = d
        self.shopsanity = s
        self.retro = r
        return self


def create_item_pool_config(world):
    world.item_pool_config = config = ItemPoolConfig()
    player_set = set()
    for player in range(1, world.players+1):
        if world.restrict_boss_items[player] != 'none':
            player_set.add(player)
        if world.restrict_boss_items[player] == 'dungeon':
            for dungeon, info in dungeon_table.items():
                if info.prize:
                    d_name = "Thieves' Town" if dungeon.startswith('Thieves') else dungeon
                    config.reserved_locations[player].add(f'{d_name} - Boss')
    for dungeon in world.dungeons:
        if world.restrict_boss_items[dungeon.player] != 'none':
            for item in dungeon.all_items:
                if item.map or item.compass:
                    item.advancement = True
    if world.algorithm == 'vanilla_bias':
        config.static_placement = {}
        config.location_groups = {}
        for player in range(1, world.players + 1):
            config.static_placement[player] = vanilla_mapping.copy()
            if world.keydropshuffle[player]:
                for item, locs in keydrop_vanilla_mapping.items():
                    if item in config.static_placement[player]:
                        config.static_placement[player][item].extend(locs)
                    else:
                        config.static_placement[player][item] = list(locs)
            # todo: shopsanity...
            # todo: retro (universal keys...)
            # retro + shops
            config.location_groups[player] = [
                LocationGroup('Major').locs(mode_grouping['Overworld Major'] + mode_grouping['Big Chests'] + mode_grouping['Heart Containers']),
                LocationGroup('bkhp').locs(mode_grouping['Heart Pieces']),
                LocationGroup('bktrash').locs(mode_grouping['Overworld Trash'] + mode_grouping['Dungeon Trash']),
                LocationGroup('bkgt').locs(mode_grouping['GT Trash'])]
            for loc_name in mode_grouping['Big Chests'] + mode_grouping['Heart Containers']:
                config.reserved_locations[player].add(loc_name)
    elif world.algorithm == 'major_bias':
        config.location_groups = [
            LocationGroup('MajorItems'),
            LocationGroup('Backup')
        ]
        config.item_pool = {}
        init_set = mode_grouping['Overworld Major'] + mode_grouping['Big Chests'] + mode_grouping['Heart Containers']
        for player in range(1, world.players + 1):
            groups = LocationGroup('Major').locs(init_set)
            if world.bigkeyshuffle[player]:
                groups.locations.extend(mode_grouping['Big Keys'])
                if world.keydropshuffle[player]:
                    groups.locations.append(mode_grouping['Big Key Drops'])
            if world.keyshuffle[player]:
                groups.locations.extend(mode_grouping['Small Keys'])
                if world.keydropshuffle[player]:
                    groups.locations.extend(mode_grouping['Key Drops'])
            if world.compassshuffle[player]:
                groups.locations.extend(mode_grouping['Compasses'])
            if world.mapshuffle[player]:
                groups.locations.extend(mode_grouping['Maps'])
            if world.shopsanity[player]:
                groups.locations.append('Capacity Upgrade - Left')
                groups.locations.append('Capacity Upgrade - Right')
            if world.retro[player]:
                if world.shopsanity[player]:
                    pass  # todo: 5 locations for single arrow representation?
            config.item_pool[player] = determine_major_items(world, player)
            config.location_groups[0].locations = set(groups.locations)
            config.reserved_locations[player].add(groups.locations)
            backup = (mode_grouping['Heart Pieces'] + mode_grouping['Dungeon Trash'] + mode_grouping['Shops']
                      + mode_grouping['Overworld Trash'] + mode_grouping['GT Trash'] + mode_grouping['RetroShops'])
            config.location_groups[1].locations = set(backup)
    elif world.algorithm == 'dungeon_bias':
        config.location_groups = [
            LocationGroup('Dungeons'),
            LocationGroup('Backup')
        ]
        config.item_pool = {}
        dungeon_set = (mode_grouping['Big Chests'] + mode_grouping['Dungeon Trash'] + mode_grouping['Big Keys'] +
                       mode_grouping['Heart Containers'] + mode_grouping['GT Trash'] + mode_grouping['Small Keys'] +
                       mode_grouping['Compasses'] + mode_grouping['Maps'] + mode_grouping['Key Drops'] +
                       mode_grouping['Big Key Drops'])
        for player in range(1, world.players + 1):
            config.item_pool[player] = determine_major_items(world, player)
            config.location_groups[0].locations = set(dungeon_set)
            backup = (mode_grouping['Heart Pieces'] + mode_grouping['Overworld Major']
                      + mode_grouping['Overworld Trash'] + mode_grouping['Shops'] + mode_grouping['RetroShops'])
            config.location_groups[1].locations = set(backup)
    elif world.algorithm == 'cluster_bias':
        config.location_groups = [
            LocationGroup('Clusters'),
        ]
        item_cnt = defaultdict(int)
        config.item_pool = {}
        for player in range(1, world.players + 1):
            config.item_pool[player] = determine_major_items(world, player)
            item_cnt[player] += count_major_items(world, player)
        # set cluster choices
        cluster_choices = figure_out_clustered_choices(world)

        chosen_locations = defaultdict(set)
        placeholder_cnt = 0
        for player in range(1, world.players + 1):
            number_of_clusters = ceil(item_cnt[player] / 13)
            location_cnt = 0
            while item_cnt[player] > location_cnt:
                chosen_clusters = random.sample(cluster_choices[player], number_of_clusters)
                for loc_group in chosen_clusters:
                    for location in loc_group.locations:
                        if not location_prefilled(location, world, player):
                            world.item_pool_config.reserved_locations[player].add(location)
                            chosen_locations[location].add(player)
                            location_cnt += 1
                cluster_choices[player] = [x for x in cluster_choices[player] if x not in chosen_clusters]
                number_of_clusters = 1
            placeholder_cnt += location_cnt - item_cnt[player]
        config.placeholders = placeholder_cnt
        config.location_groups[0].locations = chosen_locations
    elif world.algorithm == 'entangled' and world.players > 1:
        config.location_groups = [
            LocationGroup('Entangled'),
        ]
        item_cnt = 0
        config.item_pool = {}
        limits = {}
        for player in range(1, world.players + 1):
            config.item_pool[player] = determine_major_items(world, player)
            item_cnt += count_major_items(world, player)
            limits[player] = calc_dungeon_limits(world, player)
        c_set = {}
        for location in world.get_locations():
            if location.real and not location.forced_item:
                c_set[location.name] = None
        # todo: retroshop locations are created later, so count them here?
        ttl_locations, candidates = 0, list(c_set.keys())
        chosen_locations = defaultdict(set)
        random.shuffle(candidates)
        while ttl_locations < item_cnt:
            choice = candidates.pop()
            dungeon = world.get_location(choice, 1).parent_region.dungeon
            if dungeon:
                for player in range(1, world.players + 1):
                    location = world.get_location(choice, player)
                    if location.real and not location.forced_item:
                        if isinstance(limits[player], int):
                            if limits[player] > 0:
                                config.reserved_locations[player].add(choice)
                                limits[player] -= 1
                                chosen_locations[choice].add(player)
                        else:
                            previous = previously_reserved(location, world, player)
                            if limits[player][dungeon.name] > 0 or previous:
                                if validate_reservation(location, dungeon, world, player):
                                    if not previous:
                                        limits[player][dungeon.name] -= 1
                                    chosen_locations[choice].add(player)
            else:  # not dungeon restricted
                for player in range(1, world.players + 1):
                    location = world.get_location(choice, player)
                    if location.real and not location.forced_item:
                        chosen_locations[choice].add(player)
            ttl_locations += len(chosen_locations[choice])
        config.placeholders = ttl_locations - item_cnt
        config.location_groups[0].locations = chosen_locations


def location_prefilled(location, world, player):
    if world.swords[player] == 'vanilla':
        return location in vanilla_swords
    if world.goal[player] == 'pedestal':
        return location == 'Master Sword Pedestal'
    return False


def previously_reserved(location, world, player):
    if '- Boss' in location.name:
        if world.restrict_boss_items[player] == 'mapcompass' and (not world.compassshuffle[player]
                                                                  or not world.mapshuffle[player]):
            return True
        if world.restrict_boss_items[player] == 'dungeon' and (not world.compassshuffle[player]
                                                               or not world.mapshuffle[player]
                                                               or not world.bigkeyshuffle[player]
                                                               or not (world.keyshuffle[player] or world.retro[player])):
            return True
    return False


def massage_item_pool(world):
    player_pool = defaultdict(list)
    for item in world.itempool:
        player_pool[item.player].append(item)
    for dungeon in world.dungeons:
        for item in dungeon.all_items:
            if (not item.compass and not item.map) or item not in player_pool[item.player]:
                player_pool[item.player].append(item)
    player_locations = defaultdict(list)
    for player in player_pool:
        player_locations[player] = [x for x in world.get_unfilled_locations(player) if '- Prize' not in x.name]
        discrepancy = len(player_pool[player]) - len(player_locations[player])
        if discrepancy:
            trash_options = [x for x in player_pool[player] if x.name in trash_items]
            random.shuffle(trash_options)
            trash_options = sorted(trash_options, key=lambda x: trash_items[x.name], reverse=True)
            while discrepancy > 0 and len(trash_options) > 0:
                deleted = trash_options.pop()
                world.itempool.remove(deleted)
                discrepancy -= 1
            if discrepancy > 0:
                logging.getLogger('').warning(f'Too many good items in pool, something will be removed at random')
    if world.item_pool_config.placeholders is not None:
        removed = 0
        single_rupees = [item for item in world.itempool if item.name == 'Rupee (1)']
        removed += len(single_rupees)
        for x in single_rupees:
            world.itempool.remove(x)
        if removed < world.item_pool_config.placeholders:
            trash_options = [x for x in world.itempool if x.name in trash_items]
            random.shuffle(trash_options)
            trash_options = sorted(trash_options, key=lambda x: trash_items[x.name], reverse=True)
            while removed < world.item_pool_config.placeholders:
                if len(trash_options) == 0:
                    logging.getLogger('').warning(f'Too many good items in pool, not enough room for placeholders')
                deleted = trash_options.pop()
                world.itempool.remove(deleted)
                removed += 1
        if world.item_pool_config.placeholders > len(single_rupees):
            for _ in range(world.item_pool_config.placeholders-len(single_rupees)):
                single_rupees.append(ItemFactory('Rupee (1)', random.randint(1, world.players)))
        placeholders = random.sample(single_rupees, world.item_pool_config.placeholders)
        world.itempool += placeholders
        removed -= len(placeholders)
        for _ in range(removed):
            world.itempool.append(ItemFactory('Rupees (5)', random.randint(1, world.players)))


def replace_trash_item(item_pool, replacement):
    trash_options = [x for x in item_pool if x.name in trash_items]
    random.shuffle(trash_options)
    trash_options = sorted(trash_options, key=lambda x: trash_items[x.name], reverse=True)
    if len(trash_options) == 0:
        logging.getLogger('').warning(f'Too many good items in pool, not enough room for placeholders')
    deleted = trash_options.pop()
    item_pool.remove(deleted)
    replace_item = ItemFactory(replacement, deleted.player)
    item_pool.append(replace_item)
    return replace_item


def validate_reservation(location, dungeon, world, player):
    world.item_pool_config.reserved_locations[player].add(location.name)
    if world.doorShuffle[player] != 'vanilla':
        return True  # we can generate the dungeon somehow most likely
    if validate_vanilla_reservation(dungeon, world, player):
        return True
    world.item_pool_config.reserved_locations[player].remove(location.name)
    return False


def count_major_items(world, player):
    major_item_set = 52
    if world.bigkeyshuffle[player]:
        major_item_set += 11
        if world.keydropshuffle[player]:
            major_item_set += 1
        if world.doorShuffle[player] == 'crossed':
            major_item_set += 1
    if world.keyshuffle[player]:
        major_item_set += 29
        if world.keydropshuffle[player]:
            major_item_set += 32
    if world.compassshuffle[player]:
        major_item_set += 11
        if world.doorShuffle[player] == 'crossed':
            major_item_set += 2
    if world.mapshuffle[player]:
        major_item_set += 12
        if world.doorShuffle[player] == 'crossed':
            major_item_set += 1
    if world.shopsanity[player]:
        major_item_set += 2
        if world.retro[player]:
            major_item_set += 5  # the single arrow quiver
    if world.goal == 'triforcehunt':
        major_item_set += world.triforce_pool[player]
    if world.bombbag[player]:
        major_item_set += world.triforce_pool[player]
    if world.swords[player] != "random":
        if world.swords[player] == 'assured':
            major_item_set -= 1
        if world.swords[player] in ['vanilla', 'swordless']:
            major_item_set -= 4
    if world.retro[player]:
        if world.shopsanity[player]:
            major_item_set -= 1  # sword in old man cave
        if world.keyshuffle[player]:
            major_item_set -= 29
        # universal keys
        major_item_set += 19 if world.difficulty[player] == 'normal' else 14
        if world.mode[player] == 'standard' and world.doorShuffle[player] == 'vanilla':
            major_item_set -= 1  # a key in escape
        if world.doorShuffle[player] != 'vanilla':
            major_item_set += 10  # tries to add up to 10 more universal keys for door rando
    # todo: starting equipment?
    return major_item_set


def calc_dungeon_limits(world, player):
    b, s, c, m, k, r, bi = (world.bigkeyshuffle[player], world.keyshuffle[player], world.compassshuffle[player],
                            world.mapshuffle[player], world.keydropshuffle[player], world.retro[player],
                            world.restrict_boss_items[player])
    if world.doorShuffle[player] in ['vanilla', 'basic']:
        limits = {}
        for dungeon, info in dungeon_table.items():
            val = info.free_items
            if bi != 'none' and info.prize:
                if bi == 'mapcompass' and (not c or not m):
                    val -= 1
                if bi == 'dungeon' and (not c or not m or not (s or r) or not b):
                    val -= 1
            if b:
                val += 1 if info.bk_present else 0
                if k:
                    val += 1 if info.bk_drops else 0
            if s or r:
                val += info.key_num
                if k:
                    val += info.key_drops
            if c:
                val += 1 if info.compass_present else 0
            if m:
                val += 1 if info.map_present else 0
            limits[dungeon] = val
    else:
        limits = 60
        if world.bigkeyshuffle[player]:
            limits += 11
            if world.keydropshuffle[player]:
                limits += 1
        if world.keyshuffle[player] or world.retro[player]:
            limits += 29
            if world.keydropshuffle[player]:
                limits += 32
        if world.compassshuffle[player]:
            limits += 11
        if world.mapshuffle[player]:
            limits += 12
    return limits


def determine_major_items(world, player):
    major_item_set = set(major_items)
    if world.bigkeyshuffle[player]:
        major_item_set.update({x for x, y in item_table.items() if y[2] == 'BigKey'})
    if world.keyshuffle[player]:
        major_item_set.update({x for x, y in item_table.items() if y[2] == 'SmallKey'})
    if world.compassshuffle[player]:
        major_item_set.update({x for x, y in item_table.items() if y[2] == 'Compass'})
    if world.mapshuffle[player]:
        major_item_set.update({x for x, y in item_table.items() if y[2] == 'Map'})
    if world.shopsanity[player]:
        major_item_set.add('Bomb Upgrade (+5)')
        major_item_set.add('Arrow Upgrade (+5)')
    if world.retro[player]:
        major_item_set.add('Single Arrow')
        major_item_set.add('Small Key (Universal)')
    if world.goal == 'triforcehunt':
        major_item_set.add('Triforce Piece')
    if world.bombbag[player]:
        major_item_set.add('Bomb Upgrade (+10)')
    return major_item_set


def classify_major_items(world):
    if world.algorithm in ['major_bias', 'dungeon_bias', 'cluster_bias'] or (world.algorithm == 'entangled'
                                                                             and world.players > 1):
        config = world.item_pool_config
        for item in world.itempool:
            if item.name in config.item_pool[item.player]:
                if not item.advancement or not item.priority:
                    if item.smallkey or item.bigkey:
                        item.advancement = True
                    else:
                        item.priority = True


def figure_out_clustered_choices(world):
    cluster_candidates = {}
    for player in range(1, world.players + 1):
        cluster_candidates[player] = [LocationGroup(x.name).locs(x.locations) for x in clustered_groups]
        backups = list(reversed(leftovers))
        if world.bigkeyshuffle[player]:
            bk_grp = LocationGroup('BigKeys').locs(mode_grouping['Big Keys'])
            if world.keydropshuffle[player]:
                bk_grp.locations.append(mode_grouping['Big Key Drops'])
            for i in range(13-len(bk_grp.locations)):
                bk_grp.locations.append(backups.pop())
            cluster_candidates[player].append(bk_grp)
        if world.compassshuffle[player]:
            cmp_grp = LocationGroup('Compasses').locs(mode_grouping['Compasses'])
            if len(cmp_grp.locations) + len(backups) >= 13:
                for i in range(13-len(cmp_grp.locations)):
                    cmp_grp.locations.append(backups.pop())
                cluster_candidates[player].append(cmp_grp)
            else:
                backups.extend(reversed(cmp_grp.locations))
        if world.mapshuffle[player]:
            mp_grp = LocationGroup('Maps').locs(mode_grouping['Maps'])
            if len(mp_grp.locations) + len(backups) >= 13:
                for i in range(13-len(mp_grp.locations)):
                    mp_grp.locations.append(backups.pop())
                cluster_candidates[player].append(mp_grp)
            else:
                backups.extend(reversed(mp_grp.locations))
        if world.shopsanity[player]:
            cluster_candidates[player].append(LocationGroup('Shopsanity1').locs(other_clusters['Shopsanity1']))
            cluster_candidates[player].append(LocationGroup('Shopsanity2').locs(other_clusters['Shopsanity2']))
            extras = list(other_clusters['ShopsanityLeft'])
            if world.retro[player]:
                extras.extend(mode_grouping['RetroShops'])
            if len(extras)+len(backups) >= 13:
                for i in range(13-len(extras)):
                    extras.append(backups.pop())
                cluster_candidates[player].append(LocationGroup('ShopExtra').locs(extras))
            else:
                backups.extend(reversed(extras))
        if world.keyshuffle[player] or world.retro[player]:
            cluster_candidates[player].append(LocationGroup('SmallKey1').locs(other_clusters['SmallKey1']))
            cluster_candidates[player].append(LocationGroup('SmallKey2').locs(other_clusters['SmallKey2']))
            extras = list(other_clusters['SmallKeyLeft'])
            if world.keydropshuffle[player]:
                cluster_candidates[player].append(LocationGroup('KeyDrop1').locs(other_clusters['KeyDrop1']))
                cluster_candidates[player].append(LocationGroup('KeyDrop2').locs(other_clusters['KeyDrop2']))
                extras.extend(other_clusters['KeyDropLeft'])
            if len(extras)+len(backups) >= 13:
                for i in range(13-len(extras)):
                    extras.append(backups.pop())
                cluster_candidates[player].append(LocationGroup('SmallKeyExtra').locs(extras))
            else:
                backups.extend(reversed(extras))
        return cluster_candidates


def vanilla_fallback(item_to_place, locations, world):
    if item_to_place.is_inside_dungeon_item(world):
        return [x for x in locations if x.name in vanilla_fallback_dungeon_set
                and x.parent_region.dungeon and x.parent_region.dungeon.name == item_to_place.dungeon]
    return []


def filter_locations(item_to_place, locations, world):
    if world.algorithm == 'vanilla_bias':
        config, filtered = world.item_pool_config, []
        item_name = 'Bottle' if item_to_place.name.startswith('Bottle') else item_to_place.name
        if item_name in config.static_placement[item_to_place.player]:
            restricted = config.static_placement[item_to_place.player][item_name]
            filtered = [l for l in locations if l.player == item_to_place.player and l.name in restricted]
        i = 0
        while len(filtered) <= 0:
            if i >= len(config.location_groups[item_to_place.player]):
                return locations
            restricted = config.location_groups[item_to_place.player][i].locations
            filtered = [l for l in locations if l.player == item_to_place.player and l.name in restricted]
            i += 1
        return filtered
    if world.algorithm in ['major_bias', 'dungeon_bias']:
        config = world.item_pool_config
        if item_to_place.name in config.item_pool[item_to_place.player]:
            restricted = config.location_groups[0].locations
            filtered = [l for l in locations if l.name in restricted]
            if len(filtered) == 0:
                restricted = config.location_groups[1].locations
                filtered = [l for l in locations if l.name in restricted]
                # bias toward certain location in overflow? (thinking about this for major_bias)
            return filtered if len(filtered) > 0 else locations
    if (world.algorithm == 'entangled' and world.players > 1) or world.algorithm == 'cluster_bias':
        config = world.item_pool_config
        if item_to_place == 'Placeholder' or item_to_place.name in config.item_pool[item_to_place.player]:
            restricted = config.location_groups[0].locations
            filtered = [l for l in locations if l.name in restricted and l.player in restricted[l.name]]
            return filtered if len(filtered) > 0 else locations
    return locations


vanilla_mapping = {
    'Green Pendant': ['Eastern Palace - Prize'],
    'Red Pendant': ['Desert Palace - Prize', 'Tower of Hera - Prize'],
    'Blue Pendant': ['Desert Palace - Prize', 'Tower of Hera - Prize'],
    'Crystal 1': ['Palace of Darkness - Prize', 'Swamp Palace - Prize', 'Thieves\' Town - Prize',
                  'Skull Woods - Prize', 'Turtle Rock - Prize'],
    'Crystal 2': ['Palace of Darkness - Prize', 'Swamp Palace - Prize', 'Thieves\' Town - Prize',
                  'Skull Woods - Prize', 'Turtle Rock - Prize'],
    'Crystal 3': ['Palace of Darkness - Prize', 'Swamp Palace - Prize', 'Thieves\' Town - Prize',
                  'Skull Woods - Prize', 'Turtle Rock - Prize'],
    'Crystal 4': ['Palace of Darkness - Prize', 'Swamp Palace - Prize', 'Thieves\' Town - Prize',
                  'Skull Woods - Prize', 'Turtle Rock - Prize'],
    'Crystal 7': ['Palace of Darkness - Prize', 'Swamp Palace - Prize', 'Thieves\' Town - Prize',
                  'Skull Woods - Prize', 'Turtle Rock - Prize'],
    'Crystal 5': ['Ice Palace - Prize', 'Misery Mire - Prize'],
    'Crystal 6': ['Ice Palace - Prize', 'Misery Mire - Prize'],
    'Bow': ['Eastern Palace - Big Chest'],
    'Progressive Bow': ['Eastern Palace - Big Chest', 'Pyramid Fairy - Right'],
    'Book of Mudora': ['Library'],
    'Hammer': ['Palace of Darkness - Big Chest'],
    'Hookshot': ['Swamp Palace - Big Chest'],
    'Magic Mirror': ['Old Man'],
    'Ocarina': ['Flute Spot'],
    'Pegasus Boots': ['Sahasrahla'],
    'Power Glove': ['Desert Palace - Big Chest'],
    'Cape': ["King's Tomb"],
    'Mushroom': ['Mushroom'],
    'Shovel': ['Stumpy'],
    'Lamp': ["Link's House"],
    'Magic Powder': ['Potion Shop'],
    'Moon Pearl': ['Tower of Hera - Big Chest'],
    'Cane of Somaria': ['Misery Mire - Big Chest'],
    'Fire Rod': ['Skull Woods - Big Chest'],
    'Flippers': ['King Zora'],
    'Ice Rod': ['Ice Rod Cave'],
    'Titans Mitts': ["Thieves' Town - Big Chest"],
    'Bombos': ['Bombos Tablet'],
    'Ether': ['Ether Tablet'],
    'Quake': ['Catfish'],
    'Bottle': ['Bottle Merchant', 'Kakariko Tavern', 'Purple Chest', 'Hobo'],
    'Master Sword': ['Master Sword Pedestal'],
    'Tempered Sword': ['Blacksmith'],
    'Fighter Sword': ["Link's Uncle"],
    'Golden Sword': ['Pyramid Fairy - Left'],
    'Progressive Sword': ["Link's Uncle", 'Blacksmith', 'Master Sword Pedestal', 'Pyramid Fairy - Left'],
    'Progressive Glove': ['Desert Palace - Big Chest', "Thieves' Town - Big Chest"],
    'Silver Arrows': ['Pyramid Fairy - Right'],
    'Single Arrow': ['Palace of Darkness - Dark Basement - Left'],
    'Arrows (10)': ['Chicken House', 'Mini Moldorm Cave - Far Right', 'Sewers - Secret Room - Right',
                    'Paradox Cave Upper - Right', 'Mire Shed - Right', 'Ganons Tower - Hope Room - Left',
                    'Ganons Tower - Compass Room - Bottom Right', 'Ganons Tower - DMs Room - Top Right',
                    'Ganons Tower - Randomizer Room - Top Left', 'Ganons Tower - Randomizer Room - Top Right',
                    "Ganons Tower - Bob's Chest", 'Ganons Tower - Big Key Room - Left'],
    'Bombs (3)': ['Floodgate Chest', "Sahasrahla's Hut - Middle", 'Kakariko Well - Bottom', 'Superbunny Cave - Top',
                  'Mini Moldorm Cave - Far Left', 'Sewers - Secret Room - Left', 'Paradox Cave Upper - Left',
                  "Thieves' Town - Attic", 'Ice Palace - Freezor Chest', 'Palace of Darkness - Dark Maze - Top',
                  'Ganons Tower - Hope Room - Right', 'Ganons Tower - DMs Room - Top Left',
                  'Ganons Tower - Randomizer Room - Bottom Left', 'Ganons Tower - Randomizer Room - Bottom Right',
                  'Ganons Tower - Big Key Room - Right', 'Ganons Tower - Mini Helmasaur Room - Left',
                  'Ganons Tower - Mini Helmasaur Room - Right'],
    'Blue Mail': ['Ice Palace - Big Chest'],
    'Red Mail': ['Ganons Tower - Big Chest'],
    'Progressive Armor': ['Ice Palace - Big Chest', 'Ganons Tower - Big Chest'],
    'Blue Boomerang': ['Hyrule Castle - Boomerang Chest'],
    'Red Boomerang': ['Waterfall Fairy - Left'],
    'Blue Shield': ['Secret Passage'],
    'Red Shield': ['Waterfall Fairy - Right'],
    'Mirror Shield': ['Turtle Rock - Big Chest'],
    'Progressive Shield': ['Secret Passage', 'Waterfall Fairy - Right', 'Turtle Rock - Big Chest'],
    'Bug Catching Net': ['Sick Kid'],
    'Cane of Byrna': ['Spike Cave'],
    'Boss Heart Container': ['Desert Palace - Boss', 'Eastern Palace - Boss', 'Tower of Hera - Boss',
                             'Swamp Palace - Boss', "Thieves' Town - Boss", 'Skull Woods - Boss', 'Ice Palace - Boss',
                             'Misery Mire - Boss', 'Turtle Rock - Boss', 'Palace of Darkness - Boss'],
    'Sanctuary Heart Container': ['Sanctuary'],
    'Piece of Heart': ['Sunken Treasure', "Blind's Hideout - Top", "Zora's Ledge", "Aginah's Cave", 'Maze Race',
                       'Kakariko Well - Top', 'Lost Woods Hideout', 'Lumberjack Tree', 'Cave 45', 'Graveyard Cave',
                       'Checkerboard Cave', 'Bonk Rock Cave', 'Lake Hylia Island', 'Desert Ledge', 'Spectacle Rock',
                       'Spectacle Rock Cave', 'Pyramid', 'Digging Game', 'Peg Cave', 'Chest Game', 'Bumper Cave Ledge',
                       'Mire Shed - Left', 'Floating Island', 'Mimic Cave'],
    'Rupee (1)': ['Turtle Rock - Eye Bridge - Top Right', 'Ganons Tower - Compass Room - Top Right'],
    'Rupees (5)': ["Hyrule Castle - Zelda's Chest", 'Turtle Rock - Eye Bridge - Top Left',
                   # 'Palace of Darkness - Harmless Hellway',
                   'Palace of Darkness - Dark Maze - Bottom',
                   'Ganons Tower - Validation Chest'],
    'Rupees (20)': ["Blind's Hideout - Left", "Blind's Hideout - Right", "Blind's Hideout - Far Left",
                    "Blind's Hideout - Far Right", 'Kakariko Well - Left', 'Kakariko Well - Middle',
                    'Kakariko Well - Right', 'Mini Moldorm Cave - Left', 'Mini Moldorm Cave - Right',
                    'Paradox Cave Lower - Far Left', 'Paradox Cave Lower - Left', 'Paradox Cave Lower - Right',
                    'Paradox Cave Lower - Far Right', 'Paradox Cave Lower - Middle', 'Hype Cave - Top',
                    'Hype Cave - Middle Right', 'Hype Cave - Middle Left', 'Hype Cave - Bottom',
                    'Swamp Palace - West Chest', 'Swamp Palace - Flooded Room - Left', 'Swamp Palace - Waterfall Room',
                    'Swamp Palace - Flooded Room - Right', "Thieves' Town - Ambush Chest",
                    'Turtle Rock - Eye Bridge - Bottom Right', 'Ganons Tower - Compass Room - Bottom Left',
                    'Swamp Palace - Flooded Room - Right', "Thieves' Town - Ambush Chest",
                    'Ganons Tower - DMs Room - Bottom Left', 'Ganons Tower - DMs Room - Bottom Right'],
    'Rupees (50)': ["Sahasrahla's Hut - Left", "Sahasrahla's Hut - Right", 'Spiral Cave', 'Superbunny Cave - Bottom',
                    'Hookshot Cave - Top Right', 'Hookshot Cave - Top Left', 'Hookshot Cave - Bottom Right',
                    'Hookshot Cave - Bottom Left'],
    'Rupees (100)': ['Eastern Palace - Cannonball Chest'],
    'Rupees (300)': ['Mini Moldorm Cave - Generous Guy', 'Sewers - Secret Room - Middle', 'Hype Cave - Generous Guy',
                     'Brewery', 'C-Shaped House'],
    'Magic Upgrade (1/2)': ['Magic Bat'],
    'Big Key (Eastern Palace)': ['Eastern Palace - Big Key Chest'],
    'Compass (Eastern Palace)': ['Eastern Palace - Compass Chest'],
    'Map (Eastern Palace)': ['Eastern Palace - Map Chest'],
    'Small Key (Desert Palace)': ['Desert Palace - Torch'],
    'Big Key (Desert Palace)': ['Desert Palace - Big Key Chest'],
    'Compass (Desert Palace)': ['Desert Palace - Compass Chest'],
    'Map (Desert Palace)': ['Desert Palace - Map Chest'],
    'Small Key (Tower of Hera)': ['Tower of Hera - Basement Cage'],
    'Big Key (Tower of Hera)': ['Tower of Hera - Big Key Chest'],
    'Compass (Tower of Hera)': ['Tower of Hera - Compass Chest'],
    'Map (Tower of Hera)': ['Tower of Hera - Map Chest'],
    'Small Key (Escape)': ['Sewers - Dark Cross'],
    'Map (Escape)': ['Hyrule Castle - Map Chest'],
    'Small Key (Agahnims Tower)': ['Castle Tower - Room 03', 'Castle Tower - Dark Maze'],
    'Small Key (Palace of Darkness)': ['Palace of Darkness - Shooter Room', 'Palace of Darkness - The Arena - Bridge',
                                       'Palace of Darkness - Stalfos Basement',
                                       'Palace of Darkness - The Arena - Ledge',
                                       'Palace of Darkness - Dark Basement - Right',
                                       'Palace of Darkness - Harmless Hellway'],
                                       # 'Palace of Darkness - Dark Maze - Bottom'],
    'Big Key (Palace of Darkness)': ['Palace of Darkness - Big Key Chest'],
    'Compass (Palace of Darkness)': ['Palace of Darkness - Compass Chest'],
    'Map (Palace of Darkness)': ['Palace of Darkness - Map Chest'],
    'Small Key (Thieves Town)': ["Thieves' Town - Blind's Cell"],
    'Big Key (Thieves Town)': ["Thieves' Town - Big Key Chest"],
    'Compass (Thieves Town)': ["Thieves' Town - Compass Chest"],
    'Map (Thieves Town)': ["Thieves' Town - Map Chest"],
    'Small Key (Skull Woods)': ['Skull Woods - Pot Prison', 'Skull Woods - Pinball Room', 'Skull Woods - Bridge Room'],
    'Big Key (Skull Woods)': ['Skull Woods - Big Key Chest'],
    'Compass (Skull Woods)': ['Skull Woods - Compass Chest'],
    'Map (Skull Woods)': ['Skull Woods - Map Chest'],
    'Small Key (Swamp Palace)': ['Swamp Palace - Entrance'],
    'Big Key (Swamp Palace)': ['Swamp Palace - Big Key Chest'],
    'Compass (Swamp Palace)': ['Swamp Palace - Compass Chest'],
    'Map (Swamp Palace)': ['Swamp Palace - Map Chest'],
    'Small Key (Ice Palace)': ['Ice Palace - Iced T Room', 'Ice Palace - Spike Room'],
    'Big Key (Ice Palace)': ['Ice Palace - Big Key Chest'],
    'Compass (Ice Palace)': ['Ice Palace - Compass Chest'],
    'Map (Ice Palace)': ['Ice Palace - Map Chest'],
    'Small Key (Misery Mire)': ['Misery Mire - Main Lobby', 'Misery Mire - Bridge Chest', 'Misery Mire - Spike Chest'],
    'Big Key (Misery Mire)': ['Misery Mire - Big Key Chest'],
    'Compass (Misery Mire)': ['Misery Mire - Compass Chest'],
    'Map (Misery Mire)': ['Misery Mire - Map Chest'],
    'Small Key (Turtle Rock)': ['Turtle Rock - Roller Room - Right', 'Turtle Rock - Chain Chomps',
                                'Turtle Rock - Crystaroller Room', 'Turtle Rock - Eye Bridge - Bottom Left'],
    'Big Key (Turtle Rock)': ['Turtle Rock - Big Key Chest'],
    'Compass (Turtle Rock)': ['Turtle Rock - Compass Chest'],
    'Map (Turtle Rock)': ['Turtle Rock - Roller Room - Left'],
    'Small Key (Ganons Tower)': ["Ganons Tower - Bob's Torch", 'Ganons Tower - Tile Room',
                                 'Ganons Tower - Firesnake Room', 'Ganons Tower - Pre-Moldorm Chest'],
    'Big Key (Ganons Tower)': ['Ganons Tower - Big Key Chest'],
    'Compass (Ganons Tower)': ['Ganons Tower - Compass Room - Top Left'],
    'Map (Ganons Tower)': ['Ganons Tower - Map Chest']
}


keydrop_vanilla_mapping = {
    'Small Key (Desert Palace)': ['Desert Palace - Desert Tiles 1 Pot Key',
                                  'Desert Palace - Beamos Hall Pot Key', 'Desert Palace - Desert Tiles 2 Pot Key'],
    'Small Key (Eastern Palace)': ['Eastern Palace - Dark Square Pot Key', 'Eastern Palace - Dark Eyegore Key Drop'],
    'Small Key (Escape)': ['Hyrule Castle - Map Guard Key Drop', 'Hyrule Castle - Boomerang Guard Key Drop',
                           'Hyrule Castle - Key Rat Key Drop'],
    'Big Key (Escape)': ['Hyrule Castle - Big Key Drop'],
    'Small Key (Agahnims Tower)': ['Castle Tower - Dark Archer Key Drop', 'Castle Tower - Circle of Pots Key Drop'],
    'Small Key (Thieves Town)': ["Thieves' Town - Hallway Pot Key", "Thieves' Town - Spike Switch Pot Key"],
    'Small Key (Skull Woods)': ['Skull Woods - West Lobby Pot Key', 'Skull Woods - Spike Corner Key Drop'],
    'Small Key (Swamp Palace)': ['Swamp Palace - Pot Row Pot Key', 'Swamp Palace - Trench 1 Pot Key',
                                 'Swamp Palace - Hookshot Pot Key', 'Swamp Palace - Trench 2 Pot Key',
                                 'Swamp Palace - Waterway Pot Key'],
    'Small Key (Ice Palace)': ['Ice Palace - Jelly Key Drop', 'Ice Palace - Conveyor Key Drop',
                               'Ice Palace - Hammer Block Key Drop', 'Ice Palace - Many Pots Pot Key'],
    'Small Key (Misery Mire)': ['Misery Mire - Spikes Pot Key',
                                'Misery Mire - Fishbone Pot Key', 'Misery Mire - Conveyor Crystal Key Drop'],
    'Small Key (Turtle Rock)': ['Turtle Rock - Pokey 1 Key Drop', 'Turtle Rock - Pokey 2 Key Drop'],
    'Small Key (Ganons Tower)': ['Ganons Tower - Conveyor Cross Pot Key', 'Ganons Tower - Double Switch Pot Key',
                                 'Ganons Tower - Conveyor Star Pits Pot Key', 'Ganons Tower - Mini Helmasuar Key Drop'],
}

mode_grouping = {
    'Overworld Major': [
        "Link's Uncle", 'King Zora', "Link's House", 'Sahasrahla', 'Ice Rod Cave', 'Library',
        'Master Sword Pedestal', 'Old Man', 'Ether Tablet', 'Catfish', 'Stumpy', 'Bombos Tablet', 'Mushroom',
        'Bottle Merchant', 'Kakariko Tavern', 'Secret Passage', 'Flute Spot', 'Purple Chest',
        'Waterfall Fairy - Left', 'Waterfall Fairy - Right', 'Blacksmith', 'Magic Bat', 'Sick Kid', 'Hobo',
        'Potion Shop', 'Spike Cave', 'Pyramid Fairy - Left', 'Pyramid Fairy - Right', "King's Tomb",
    ],
    'Big Chests': ['Eastern Palace - Big Chest','Desert Palace - Big Chest', 'Tower of Hera - Big Chest',
                   'Palace of Darkness - Big Chest', 'Swamp Palace - Big Chest', 'Skull Woods - Big Chest',
                   "Thieves' Town - Big Chest", 'Misery Mire - Big Chest', 'Hyrule Castle - Boomerang Chest',
                   'Ice Palace - Big Chest', 'Turtle Rock - Big Chest', 'Ganons Tower - Big Chest'],
    'Heart Containers': ['Sanctuary', 'Eastern Palace - Boss','Desert Palace - Boss', 'Tower of Hera - Boss',
                         'Palace of Darkness - Boss', 'Swamp Palace - Boss', 'Skull Woods - Boss',
                         "Thieves' Town - Boss", 'Ice Palace - Boss', 'Misery Mire - Boss', 'Turtle Rock - Boss'],
    'Heart Pieces': [
        'Bumper Cave Ledge', 'Desert Ledge', 'Lake Hylia Island', 'Floating Island',
        'Maze Race', 'Spectacle Rock', 'Pyramid', "Zora's Ledge", 'Lumberjack Tree',
        'Sunken Treasure', 'Spectacle Rock Cave', 'Lost Woods Hideout', 'Checkerboard Cave', 'Peg Cave', 'Cave 45',
        'Graveyard Cave', 'Kakariko Well - Top', "Blind's Hideout - Top", 'Bonk Rock Cave', "Aginah's Cave",
        'Chest Game', 'Digging Game', 'Mire Shed - Right', 'Mimic Cave'
    ],
    'Big Keys': [
        'Eastern Palace - Big Key Chest', 'Ganons Tower - Big Key Chest',
        'Desert Palace - Big Key Chest', 'Tower of Hera - Big Key Chest', 'Palace of Darkness - Big Key Chest',
        'Swamp Palace - Big Key Chest', "Thieves' Town - Big Key Chest", 'Skull Woods - Big Key Chest',
        'Ice Palace - Big Key Chest', 'Misery Mire - Big Key Chest', 'Turtle Rock - Big Key Chest',
    ],
    'Compasses': [
        'Eastern Palace - Compass Chest', 'Desert Palace - Compass Chest', 'Tower of Hera - Compass Chest',
        'Palace of Darkness - Compass Chest', 'Swamp Palace - Compass Chest', 'Skull Woods - Compass Chest',
        "Thieves' Town - Compass Chest", 'Ice Palace - Compass Chest', 'Misery Mire - Compass Chest',
        'Turtle Rock - Compass Chest', 'Ganons Tower - Compass Room - Top Left'
    ],
    'Maps': [
        'Hyrule Castle - Map Chest', 'Eastern Palace - Map Chest', 'Desert Palace - Map Chest',
        'Tower of Hera - Map Chest', 'Palace of Darkness - Map Chest', 'Swamp Palace - Map Chest',
        'Skull Woods - Map Chest', "Thieves' Town - Map Chest", 'Ice Palace - Map Chest', 'Misery Mire - Map Chest',
        'Turtle Rock - Roller Room - Left', 'Ganons Tower - Map Chest'
    ],
    'Small Keys': [
        'Sewers - Dark Cross', 'Desert Palace - Torch', 'Tower of Hera - Basement Cage',
        'Castle Tower - Room 03', 'Castle Tower - Dark Maze',
        'Palace of Darkness - Stalfos Basement',  'Palace of Darkness - Dark Basement - Right',
        'Palace of Darkness - Dark Maze - Bottom', 'Palace of Darkness - Shooter Room',
        'Palace of Darkness - The Arena - Bridge',  'Palace of Darkness - The Arena - Ledge',
        "Thieves' Town - Blind's Cell",  'Skull Woods - Bridge Room', 'Ice Palace - Spike Room',
        'Skull Woods - Pot Prison', 'Skull Woods - Pinball Room', 'Misery Mire - Spike Chest',
        'Ice Palace - Iced T Room', 'Misery Mire - Main Lobby', 'Misery Mire - Bridge Chest', 'Swamp Palace - Entrance',
        'Turtle Rock - Chain Chomps', 'Turtle Rock - Crystaroller Room', 'Turtle Rock - Roller Room - Right',
        'Turtle Rock - Eye Bridge - Bottom Left', "Ganons Tower - Bob's Torch", 'Ganons Tower - Tile Room',
        'Ganons Tower - Firesnake Room', 'Ganons Tower - Pre-Moldorm Chest'
    ],
    'Dungeon Trash': [
        'Sewers - Secret Room - Right', 'Sewers - Secret Room - Left', 'Sewers - Secret Room - Middle',
        "Hyrule Castle - Zelda's Chest", 'Eastern Palace - Cannonball Chest', "Thieves' Town - Ambush Chest",
        "Thieves' Town - Attic", 'Ice Palace - Freezor Chest', 'Palace of Darkness - Dark Basement - Left',
        'Palace of Darkness - Dark Maze - Bottom', 'Palace of Darkness - Dark Maze - Top',
        'Swamp Palace - Flooded Room - Left', 'Swamp Palace - Flooded Room - Right', 'Swamp Palace - Waterfall Room',
        'Turtle Rock - Eye Bridge - Bottom Right', 'Turtle Rock - Eye Bridge - Top Left',
        'Turtle Rock - Eye Bridge - Top Right', 'Swamp Palace - West Chest',
    ],
    'Overworld Trash': [
        "Blind's Hideout - Left", "Blind's Hideout - Right", "Blind's Hideout - Far Left",
        "Blind's Hideout - Far Right", 'Kakariko Well - Left', 'Kakariko Well - Middle', 'Kakariko Well - Right',
        'Kakariko Well - Bottom', 'Chicken House', 'Floodgate Chest', 'Mini Moldorm Cave - Left',
        'Mini Moldorm Cave - Right', 'Mini Moldorm Cave - Generous Guy', 'Mini Moldorm Cave - Far Left',
        'Mini Moldorm Cave - Far Right', "Sahasrahla's Hut - Left", "Sahasrahla's Hut - Right",
        "Sahasrahla's Hut - Middle", 'Paradox Cave Lower - Far Left', 'Paradox Cave Lower - Left',
        'Paradox Cave Lower - Right', 'Paradox Cave Lower - Far Right', 'Paradox Cave Lower - Middle',
        'Paradox Cave Upper - Left', 'Paradox Cave Upper - Right', 'Spiral Cave', 'Brewery', 'C-Shaped House',
        'Hype Cave - Top', 'Hype Cave - Middle Right', 'Hype Cave - Middle Left', 'Hype Cave - Bottom',
        'Hype Cave - Generous Guy', 'Superbunny Cave - Bottom', 'Superbunny Cave - Top', 'Hookshot Cave - Top Right',
        'Hookshot Cave - Top Left', 'Hookshot Cave - Bottom Right', 'Hookshot Cave - Bottom Left', 'Mire Shed - Left'
    ],
    'GT Trash': [
        'Ganons Tower - DMs Room - Top Right', 'Ganons Tower - DMs Room - Top Left',
        'Ganons Tower - DMs Room - Bottom Left', 'Ganons Tower - DMs Room - Bottom Right',
        'Ganons Tower - Compass Room - Top Right', 'Ganons Tower - Compass Room - Bottom Right',
        'Ganons Tower - Compass Room - Bottom Left', 'Ganons Tower - Hope Room - Left',
        'Ganons Tower - Hope Room - Right', 'Ganons Tower - Randomizer Room - Top Left',
        'Ganons Tower - Randomizer Room - Top Right', 'Ganons Tower - Randomizer Room - Bottom Right',
        'Ganons Tower - Randomizer Room - Bottom Left', "Ganons Tower - Bob's Chest",
        'Ganons Tower - Big Key Room - Left', 'Ganons Tower - Big Key Room - Right',
        'Ganons Tower - Mini Helmasaur Room - Left', 'Ganons Tower - Mini Helmasaur Room - Right',
        'Ganons Tower - Validation Chest',
    ],
    'Key Drops': [
        'Hyrule Castle - Map Guard Key Drop', 'Hyrule Castle - Boomerang Guard Key Drop',
        'Hyrule Castle - Key Rat Key Drop', 'Eastern Palace - Dark Square Pot Key',
        'Eastern Palace - Dark Eyegore Key Drop', 'Desert Palace - Desert Tiles 1 Pot Key',
        'Desert Palace - Beamos Hall Pot Key', 'Desert Palace - Desert Tiles 2 Pot Key',
        'Castle Tower - Dark Archer Key Drop', 'Castle Tower - Circle of Pots Key Drop',
        'Swamp Palace - Pot Row Pot Key', 'Swamp Palace - Trench 1 Pot Key', 'Swamp Palace - Hookshot Pot Key',
        'Swamp Palace - Trench 2 Pot Key', 'Swamp Palace - Waterway Pot Key', 'Skull Woods - West Lobby Pot Key',
        'Skull Woods - Spike Corner Key Drop', "Thieves' Town - Hallway Pot Key",
        "Thieves' Town - Spike Switch Pot Key", 'Ice Palace - Jelly Key Drop', 'Ice Palace - Conveyor Key Drop',
        'Ice Palace - Hammer Block Key Drop', 'Ice Palace - Many Pots Pot Key', 'Misery Mire - Spikes Pot Key',
        'Misery Mire - Fishbone Pot Key', 'Misery Mire - Conveyor Crystal Key Drop', 'Turtle Rock - Pokey 1 Key Drop',
        'Turtle Rock - Pokey 2 Key Drop', 'Ganons Tower - Conveyor Cross Pot Key',
        'Ganons Tower - Double Switch Pot Key', 'Ganons Tower - Conveyor Star Pits Pot Key',
        'Ganons Tower - Mini Helmasuar Key Drop',
    ],
    'Big Key Drops': ['Hyrule Castle - Big Key Drop'],
    'Shops': [
        'Dark Death Mountain Shop - Left', 'Dark Death Mountain Shop - Middle', 'Dark Death Mountain Shop - Right',
        'Red Shield Shop - Left', 'Red Shield Shop - Middle', 'Red Shield Shop - Right', 'Dark Lake Hylia Shop - Left',
        'Dark Lake Hylia Shop - Middle', 'Dark Lake Hylia Shop - Right', 'Dark Lumberjack Shop - Left',
        'Dark Lumberjack Shop - Middle', 'Dark Lumberjack Shop - Right', 'Village of Outcasts Shop - Left',
        'Village of Outcasts Shop - Middle', 'Village of Outcasts Shop - Right', 'Dark Potion Shop - Left',
        'Dark Potion Shop - Middle', 'Dark Potion Shop - Right', 'Paradox Shop - Left', 'Paradox Shop - Middle',
        'Paradox Shop - Right', 'Kakariko Shop - Left', 'Kakariko Shop - Middle', 'Kakariko Shop - Right',
        'Lake Hylia Shop - Left', 'Lake Hylia Shop - Middle', 'Lake Hylia Shop - Right', 'Capacity Upgrade - Left',
        'Capacity Upgrade - Right'
    ],
    'RetroShops': [
        'Old Man Sword Cave Item 1', 'Take-Any #1 Item 1', 'Take-Any #1 Item 2', 'Take-Any #2 Item 1',
        'Take-Any #2 Item 2', 'Take-Any #3 Item 1', 'Take-Any #3 Item 2','Take-Any #4 Item 1', 'Take-Any #4 Item 2'
    ]
}

vanilla_fallback_dungeon_set = set(mode_grouping['Dungeon Trash'] + mode_grouping['Big Keys'] +
                                   mode_grouping['GT Trash'] + mode_grouping['Small Keys'] +
                                   mode_grouping['Compasses'] + mode_grouping['Maps'] + mode_grouping['Key Drops'] +
                                   mode_grouping['Big Key Drops'])


major_items = {'Bombos', 'Book of Mudora', 'Cane of Somaria', 'Ether', 'Fire Rod', 'Flippers', 'Ocarina', 'Hammer',
               'Hookshot', 'Ice Rod', 'Lamp', 'Cape', 'Magic Powder', 'Mushroom', 'Pegasus Boots', 'Quake', 'Shovel',
               'Bug Catching Net', 'Cane of Byrna', 'Blue Boomerang', 'Red Boomerang', 'Progressive Glove',
               'Power Glove', 'Titans Mitts', 'Bottle', 'Bottle (Red Potion)', 'Bottle (Green Potion)', 'Magic Mirror',
               'Bottle (Blue Potion)', 'Bottle (Fairy)', 'Bottle (Bee)', 'Bottle (Good Bee)', 'Magic Upgrade (1/2)',
               'Sanctuary Heart Container', 'Boss Heart Container', 'Progressive Shield', 'Blue Shield', 'Red Shield',
               'Mirror Shield', 'Progressive Armor', 'Blue Mail', 'Red Mail', 'Progressive Sword', 'Fighter Sword',
               'Master Sword', 'Tempered Sword', 'Golden Sword', 'Bow', 'Silver Arrows', 'Triforce Piece', 'Moon Pearl',
               'Progressive Bow', 'Progressive Bow (Alt)'}


clustered_groups = [
    LocationGroup("MajorRoute1").locs([
        'Ice Rod Cave', 'Library', 'Old Man', 'Magic Bat', 'Ether Tablet', 'Hobo', 'Purple Chest', 'Spike Cave',
        'Sahasrahla', 'Superbunny Cave - Bottom', 'Superbunny Cave - Top',
        'Ganons Tower - Randomizer Room - Bottom Left', 'Ganons Tower - Randomizer Room - Bottom Right'
    ]),
    LocationGroup("MajorRoute2").locs([
        'Mushroom', 'Secret Passage', 'Bottle Merchant', 'Flute Spot', 'Catfish', 'Stumpy', 'Waterfall Fairy - Left',
        'Waterfall Fairy - Right', 'Master Sword Pedestal', "Thieves' Town - Attic", 'Sewers - Secret Room - Right',
        'Sewers - Secret Room - Left', 'Sewers - Secret Room - Middle'
    ]),
    LocationGroup("MajorRoute3").locs([
        'Kakariko Tavern', 'Sick Kid', 'King Zora', 'Potion Shop', 'Bombos Tablet', "King's Tomb", 'Blacksmith',
        'Pyramid Fairy - Left', 'Pyramid Fairy - Right', 'Hookshot Cave - Top Right', 'Hookshot Cave - Top Left',
        'Hookshot Cave - Bottom Right', 'Hookshot Cave - Bottom Left'
    ]),
    LocationGroup("Dungeon Major").locs([
        'Eastern Palace - Big Chest', 'Desert Palace - Big Chest', 'Tower of Hera - Big Chest',
        'Palace of Darkness - Big Chest', 'Swamp Palace - Big Chest', 'Skull Woods - Big Chest',
        "Thieves' Town - Big Chest", 'Misery Mire - Big Chest', 'Hyrule Castle - Boomerang Chest',
        'Ice Palace - Big Chest', 'Turtle Rock - Big Chest', 'Ganons Tower - Big Chest', "Link's Uncle"]),
    LocationGroup("Dungeon Heart").locs([
        'Sanctuary', 'Eastern Palace - Boss', 'Desert Palace - Boss', 'Tower of Hera - Boss',
        'Palace of Darkness - Boss', 'Swamp Palace - Boss', 'Skull Woods - Boss', "Thieves' Town - Boss",
        'Ice Palace - Boss', 'Misery Mire - Boss', 'Turtle Rock - Boss', "Link's House",
        'Ganons Tower - Validation Chest']),
    LocationGroup("HeartPieces1").locs([
        'Kakariko Well - Top', 'Lost Woods Hideout', 'Maze Race', 'Lumberjack Tree', 'Bonk Rock Cave', 'Graveyard Cave',
        'Checkerboard Cave', "Zora's Ledge", 'Digging Game', 'Desert Ledge', 'Bumper Cave Ledge', 'Floating Island',
        'Swamp Palace - Waterfall Room']),
    LocationGroup("HeartPieces2").locs([
        "Blind's Hideout - Top", 'Sunken Treasure', "Aginah's Cave", 'Mimic Cave', 'Spectacle Rock Cave', 'Cave 45',
        'Spectacle Rock', 'Lake Hylia Island', 'Chest Game', 'Mire Shed - Right', 'Pyramid', 'Peg Cave',
        'Eastern Palace - Cannonball Chest']),
    LocationGroup("BlindHope").locs([
        "Blind's Hideout - Left", "Blind's Hideout - Right", "Blind's Hideout - Far Left",
        "Blind's Hideout - Far Right", 'Floodgate Chest', 'Spiral Cave', 'Palace of Darkness - Dark Maze - Bottom',
        'Palace of Darkness - Dark Maze - Top', 'Swamp Palace - Flooded Room - Left',
        'Swamp Palace - Flooded Room - Right', "Thieves' Town - Ambush Chest", 'Ganons Tower - Hope Room - Left',
        'Ganons Tower - Hope Room - Right']),
    LocationGroup('WellHype').locs([
        'Kakariko Well - Left', 'Kakariko Well - Middle', 'Kakariko Well - Right', 'Kakariko Well - Bottom',
        'Paradox Cave Upper - Left', 'Paradox Cave Upper - Right', 'Hype Cave - Top', 'Hype Cave - Middle Right',
        'Hype Cave - Middle Left', 'Hype Cave - Bottom', 'Hype Cave - Generous Guy',
        'Ganons Tower - DMs Room - Bottom Left', 'Ganons Tower - DMs Room - Bottom Right',
    ]),
    LocationGroup('MiniMoldormLasers').locs([
        'Mini Moldorm Cave - Left', 'Mini Moldorm Cave - Right', 'Mini Moldorm Cave - Generous Guy',
        'Mini Moldorm Cave - Far Left', 'Mini Moldorm Cave - Far Right', 'Chicken House', 'Brewery',
        'Palace of Darkness - Dark Basement - Left', 'Ice Palace - Freezor Chest', 'Swamp Palace - West Chest',
        'Turtle Rock - Eye Bridge - Bottom Right', 'Turtle Rock - Eye Bridge - Top Left',
        'Turtle Rock - Eye Bridge - Top Right',
    ]),
    LocationGroup('ParadoxCloset').locs([
        "Sahasrahla's Hut - Left", "Sahasrahla's Hut - Right", "Sahasrahla's Hut - Middle",
        'Paradox Cave Lower - Far Left', 'Paradox Cave Lower - Left', 'Paradox Cave Lower - Right',
        'Paradox Cave Lower - Far Right', 'Paradox Cave Lower - Middle', "Hyrule Castle - Zelda's Chest",
        'C-Shaped House', 'Mire Shed - Left', 'Ganons Tower - Compass Room - Bottom Right',
        'Ganons Tower - Compass Room - Bottom Left',
    ])
]

other_clusters = {
    'SmallKey1': [
        'Sewers - Dark Cross', 'Tower of Hera - Basement Cage', 'Palace of Darkness - Shooter Room',
        'Palace of Darkness - The Arena - Bridge', 'Palace of Darkness - Stalfos Basement',
        'Palace of Darkness - Dark Basement - Right', "Thieves' Town - Blind's Cell", 'Skull Woods - Bridge Room',
        'Ice Palace - Iced T Room', 'Misery Mire - Main Lobby', 'Misery Mire - Bridge Chest',
        'Misery Mire - Spike Chest', "Ganons Tower - Bob's Torch"],
    'SmallKey2': [
        'Desert Palace - Torch', 'Castle Tower - Room 03', 'Castle Tower - Dark Maze',
        'Palace of Darkness - The Arena - Ledge', 'Palace of Darkness - Harmless Hellway', 'Swamp Palace - Entrance',
        'Skull Woods - Pot Prison', 'Skull Woods - Pinball Room', 'Ice Palace - Spike Room',
        'Turtle Rock - Roller Room - Right', 'Turtle Rock - Chain Chomps', 'Turtle Rock - Crystaroller Room',
        'Turtle Rock - Eye Bridge - Bottom Left'],
    'SmallKeyLeft': [
        'Ganons Tower - Tile Room', 'Ganons Tower - Firesnake Room', 'Ganons Tower - Pre-Moldorm Chest'],
    'KeyDrop1': [
        'Hyrule Castle - Map Guard Key Drop', 'Hyrule Castle - Boomerang Guard Key Drop',
        'Hyrule Castle - Key Rat Key Drop', 'Swamp Palace - Hookshot Pot Key', 'Swamp Palace - Trench 2 Pot Key',
        'Swamp Palace - Waterway Pot Key', 'Skull Woods - West Lobby Pot Key', 'Skull Woods - Spike Corner Key Drop',
        'Ice Palace - Jelly Key Drop', 'Ice Palace - Conveyor Key Drop', 'Misery Mire - Spikes Pot Key',
        'Misery Mire - Fishbone Pot Key', 'Misery Mire - Conveyor Crystal Key Drop'],
    'KeyDrop2': [
        'Eastern Palace - Dark Square Pot Key', 'Eastern Palace - Dark Eyegore Key Drop',
        'Desert Palace - Desert Tiles 1 Pot Key', 'Desert Palace - Beamos Hall Pot Key',
        'Desert Palace - Desert Tiles 2 Pot Key', 'Swamp Palace - Pot Row Pot Key', 'Swamp Palace - Trench 1 Pot Key',
        "Thieves' Town - Hallway Pot Key", "Thieves' Town - Spike Switch Pot Key", 'Ice Palace - Hammer Block Key Drop',
        'Ice Palace - Many Pots Pot Key', 'Turtle Rock - Pokey 1 Key Drop', 'Turtle Rock - Pokey 2 Key Drop'],
    'KeyDropLeft': [
        'Castle Tower - Dark Archer Key Drop', 'Castle Tower - Circle of Pots Key Drop',
        'Ganons Tower - Conveyor Cross Pot Key', 'Ganons Tower - Double Switch Pot Key',
        'Ganons Tower - Conveyor Star Pits Pot Key', 'Ganons Tower - Mini Helmasuar Key Drop'],
    'Shopsanity1': [
        'Dark Lumberjack Shop - Left', 'Dark Lumberjack Shop - Middle', 'Dark Lumberjack Shop - Right',
        'Dark Lake Hylia Shop - Left', 'Dark Lake Hylia Shop - Middle', 'Dark Lake Hylia Shop - Right',
        'Paradox Shop - Left', 'Paradox Shop - Middle', 'Paradox Shop - Right',
        'Kakariko Shop - Left', 'Kakariko Shop - Middle', 'Kakariko Shop - Right', 'Capacity Upgrade - Left'],
    'Shopsanity2': [
        'Red Shield Shop - Left', 'Red Shield Shop - Middle', 'Red Shield Shop - Right',
        'Village of Outcasts Shop - Left', 'Village of Outcasts Shop - Middle', 'Village of Outcasts Shop - Right',
        'Dark Potion Shop - Left', 'Dark Potion Shop - Middle', 'Dark Potion Shop - Right',
        'Lake Hylia Shop - Left', 'Lake Hylia Shop - Middle', 'Lake Hylia Shop - Right', 'Capacity Upgrade - Right',
    ],
    'ShopsanityLeft': ['Potion Shop - Left', 'Potion Shop - Middle', 'Potion Shop - Right']
}

leftovers = [
    'Ganons Tower - DMs Room - Top Right', 'Ganons Tower - DMs Room - Top Left',
    'Ganons Tower - Compass Room - Top Right', 'Ganons Tower - Randomizer Room - Top Left',
    'Ganons Tower - Randomizer Room - Top Right',"Ganons Tower - Bob's Chest", 'Ganons Tower - Big Key Room - Left',
    'Ganons Tower - Big Key Room - Right', 'Ganons Tower - Mini Helmasaur Room - Left',
    'Ganons Tower - Mini Helmasaur Room - Right',
]

vanilla_swords = {"Link's Uncle", 'Master Sword Pedestal', 'Blacksmith', 'Pyramid Fairy - Left'}

trash_items = {
    'Nothing': -1,
    'Bee Trap': 0,
    'Rupee (1)': 1,
    'Rupees (5)': 1,
    'Rupees (20)': 1,

    'Small Heart': 2,
    'Bee': 2,

    'Bombs (3)': 3,
    'Arrows (10)': 3,
    'Bombs (10)': 3,

    'Red Potion': 4,
    'Blue Shield': 4,
    'Rupees (50)': 4,
    'Rupees (100)': 4,
    'Rupees (300)': 5,

    'Piece of Heart': 17
}
