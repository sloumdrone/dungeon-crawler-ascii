import libtcodpy as libtcod
import math
import textwrap
import shelve

"""0.24.2 changes: Added room size scaling in with a multiplier to MAX_ROOMS upon dungeon level up/down. I have found that I also need to scale the map size to make the scaling make sense. 
However, due to certain minimums, the early levels will be larger than needed, with long hallways. I'm not sure how I feel about it all. We'll see once more play testing has occurred.
The next thing to implement is stat system improvements. It is far too simple and doesn't provide a range of possibilities. After that I will expand the item and monster list. 
I'd also like toadd some portal potions that take you back to level one (a persistent level) to drop of pick up gear. Stackable healing potions would be great as well. Trap doors
could be cool as well, basically they would be stairs disguised as an item. When you grab it, it would take you down a few levels to a much more difficult area."""
 
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
CAMERA_WIDTH = 80
CAMERA_HEIGHT = 43
MAP_WIDTH = 90
MAP_HEIGHT = 90
 
#sizes/coordinates for GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
INVENTORY_WIDTH = 50
LEVEL_SCREEN_WIDTH = 40
CHARACTER_SCREEN_WIDTH = 40
 

ROOM_MAX_SIZE = 20
ROOM_MIN_SIZE = 6
MAX_ROOMS = 4
CAVE_MAX_SIZE = 70
CAVE_MIN_SIZE = 30
MAX_CAVES = 4

#leveling variables
LEVEL_UP_BASE = 100
LEVEL_UP_FACTOR = 75
 
#spell values
REST_AMOUNT = 100
LIGHTNING_DAMAGE = 40
LIGHTNING_RANGE = 5
CONFUSE_RANGE = 8
CONFUSE_NUM_TURNS = 10
FIREBALL_RADIUS = 3
FIREBALL_DAMAGE = 25
 
 
FOV_ALGO = 0  
FOV_LIGHT_WALLS = True  #light walls or not
TORCH_RADIUS = 6
 
LIMIT_FPS = 20  #20 frames-per-second maximum
 
 
color_dark_wall = libtcod.Color(5, 5, 5)
color_light_wall = libtcod.Color(63, 50, 31)
color_dark_ground = libtcod.Color(0, 0, 0)
color_light_ground = libtcod.Color(127, 101, 63)
 
 
class Tile:
    #a tile of the map and its properties
    def __init__(self, blocked, block_sight = None):
        self.blocked = blocked
 
        #all tiles start unexplored
        self.explored = False
 
        #by default, if a tile is blocked, it also blocks sight
        if block_sight is None: block_sight = blocked
        self.block_sight = block_sight
 
class Rect:
    #a rectangle on the map. used to characterize a room.
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h
 
    def center(self):
        center_x = (self.x1 + self.x2) / 2
        center_y = (self.y1 + self.y2) / 2
        return (center_x, center_y)
 
    def intersect(self, other):
        #returns true if this rectangle intersects with another one
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and
                self.y1 <= other.y2 and self.y2 >= other.y1)

class Object:
    #this is a generic object: the player, a monster, an item, the stairs...
    #it's always represented by a character on screen.
    def __init__(self, x, y, char, name, color, blocks=False, fighter=None, ai=None, item=None, equipment=None):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.blocks = blocks
        self.fighter = fighter
        if self.fighter:  #let the fighter component know who owns it
            self.fighter.owner = self
 
        self.ai = ai
        if self.ai:  #let the AI component know who owns it
            self.ai.owner = self
 
        self.item = item
        if self.item:  #let the Item component know who owns it
            self.item.owner = self

        self.equipment = equipment
        if self.equipment:  #let the Equipment component know who owns it
            self.equipment.owner = self
 
            #there must be an Item component for the Equipment component to work properly
            self.item = Item()
            self.item.owner = self
 
    def move(self, dx, dy):
        #move by the given amount, if the destination is not blocked
        if not is_blocked(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
 
    def move_towards(self, target_x, target_y):
        #vector from this object to the target, and distance
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx ** 2 + dy ** 2)
 
        #normalize it to length 1 (preserving direction), then round it and
        #convert to integer so the movement is restricted to the map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)
 
    def distance_to(self, other):
        #return the distance to another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)
 
    def distance(self, x, y):
        #return the distance to some coordinates
        return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)
 
    def send_to_back(self):
        #make this object be drawn first, so all others appear above it if they're in the same tile.
        global objects
        objects.remove(self)
        objects.insert(0, self)
 
    def draw(self):
        #only show if it's visible to the player
        if libtcod.map_is_in_fov(fov_map, self.x, self.y):
            (x, y) = to_camera_coordinates(self.x, self.y)
 
            if x is not None:
                #set the color and then draw the character that represents this object at its position
                libtcod.console_set_default_foreground(con, self.color)
                libtcod.console_put_char(con, x, y, self.char, libtcod.BKGND_NONE)
 
    def clear(self):
        #erase the character that represents this object
        (x, y) = to_camera_coordinates(self.x, self.y)
        if x is not None:
            libtcod.console_put_char(con, x, y, ' ', libtcod.BKGND_NONE)
 
 
class Fighter:
    #combat-related properties and methods (monster, player, NPC).
    def __init__(self, hp, defense, power, lore, xp, death_function=None):
        self.base_max_hp = hp
        self.hp = hp
        self.base_defense = defense
        self.base_power = power
        self.base_lore = lore
        self.xp = xp
        self.death_function = death_function
 
    @property
    def power(self):  #return actual power, by summing up the bonuses from all equipped items
        bonus = sum(equipment.power_bonus for equipment in get_all_equipped(self.owner))
        return self.base_power + bonus
 
    @property
    def defense(self):  #return actual defense, by summing up the bonuses from all equipped items
        bonus = sum(equipment.defense_bonus for equipment in get_all_equipped(self.owner))
        return self.base_defense + bonus
 
    @property
    def max_hp(self):  #return actual max_hp, by summing up the bonuses from all equipped items
        bonus = sum(equipment.max_hp_bonus for equipment in get_all_equipped(self.owner))
        return self.base_max_hp + bonus

    @property
    def lore(self):  #return actual lore, by summing up the bonuses from all equipped items
        bonus = sum(equipment.lore_bonus for equipment in get_all_equipped(self.owner))
        return self.base_lore + bonus

    def attack(self, target):
        global critical_hit
        #a formula for attack damage
        hit = (libtcod.random_get_int(0, 1, 20) + self.power) - (libtcod.random_get_int(0, 1, 20) + target.fighter.defense)
        damage = (libtcod.random_get_int(0, 1, 4) + self.power) - target.fighter.defense
        critical_hit = libtcod.random_get_int(0, 1, 20)                     

        if hit > 0 and damage > 0:
            if critical_hit > 18:
                message(self.owner.name.capitalize() + ' critically wounds ' + target.name + ' for ' + str(damage * 2) + ' hit points.')
            else:
                message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
            target.fighter.take_damage(damage)
        else:
            message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')
 
    def take_damage(self, damage):
        global critical_hit
        #apply damage if possible
        if damage > 0:
            if critical_hit > 18:
                self.hp -= (damage * 2)
            else:
                self.hp -= damage
 
            #check for death. if there's a death function, call it
            if self.hp <= 0:
                function = self.death_function
                if function is not None:
                    function(self.owner)

                if self.owner != player:  #yield experience to the player
                    player.fighter.xp += self.xp
 
    def heal(self, amount):
        #heal by the given amount, without going over the maximum
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp

    def poison(self, amount):
        #poison by the given amount
        self.hp -= amount

        if self.hp <= 0:
            function = self.death_function
            if function is not None:
                function(self.owner)
 
class BasicMonster:
    #AI for a basic monster.
    def take_turn(self):
        #a basic monster takes its turn. if you can see it, it can see you
        monster = self.owner
        if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
 
            #move towards player if far away
            if monster.distance_to(player) >= 2:
                monster.move_towards(player.x, player.y)
 
            #close enough, attack! (if the player is still alive.)
            elif player.fighter.hp > 0:
                monster.fighter.attack(player)
 
class ConfusedMonster:
    #AI for a temporarily confused monster (reverts to previous AI after a while).
    def __init__(self, old_ai, num_turns=CONFUSE_NUM_TURNS):
        self.old_ai = old_ai
        self.num_turns = num_turns
 
    def take_turn(self):
        if self.num_turns > 0:  #still confused...
            #move in a random direction, and decrease the number of turns confused
            self.owner.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
            self.num_turns -= 1
 
        else:  #restore the previous AI (this one will be deleted because it's not referenced anymore)
            self.owner.ai = self.old_ai
            message('The ' + self.owner.name + ' is no longer confused!', libtcod.red)
 
 
class Item:
    #an item that can be picked up and used.
    def __init__(self, use_function=None):
        self.use_function = use_function
 
    def pick_up(self):
        #add to the player's inventory and remove from the map
        if len(inventory) >= 26:
            message('Your inventory is full, cannot pick up ' + self.owner.name + '.', libtcod.red)
        else:
            inventory.append(self.owner)
            objects.remove(self.owner)
            message('You picked up a ' + self.owner.name + '!', libtcod.green)
 
            #special case: automatically equip, if the corresponding equipment slot is unused
            equipment = self.owner.equipment
            if equipment and get_equipped_in_slot(equipment.slot) is None:
                equipment.equip()
 
    def drop(self):
        #special case: if the object has the Equipment component, dequip it before dropping
        if self.owner.equipment:
            self.owner.equipment.dequip()

        #add to the map and remove from the player's inventory. also, place it at the player's coordinates
        objects.append(self.owner)
        inventory.remove(self.owner)
        self.owner.x = player.x
        self.owner.y = player.y
        message('You dropped a ' + self.owner.name + '.', libtcod.yellow)
 
    def use(self):
        #special case: if the object has the Equipment component, the "use" action is to equip/dequip
        if self.owner.equipment:
            self.owner.equipment.toggle_equip()
            return

        #just call the "use_function" if it is defined
        if self.use_function is None:
            message('The ' + self.owner.name + ' cannot be used.')
        else:
            if self.use_function() != 'cancelled':
                inventory.remove(self.owner)  #destroy after use, unless it was cancelled for some reason

class Equipment:
    #an object that can be equipped, yielding bonuses. automatically adds the Item component.
    def __init__(self, slot, power_bonus=0, defense_bonus=0, lore_bonus=0, max_hp_bonus=0, required_level=0):
        self.power_bonus = power_bonus
        self.defense_bonus = defense_bonus
        self.max_hp_bonus = max_hp_bonus
        self.lore_bonus = lore_bonus
        self.required_level = required_level
 
        self.slot = slot
        self.is_equipped = False
 
    def toggle_equip(self):  #toggle equip/dequip status
        if self.is_equipped:
            self.dequip()
        else:
            self.equip()
 
    def equip(self):
        #Check to see if the player is a high enough level to wield the equipment
        if player.level >= self.required_level:
            #if the slot is already being used, dequip whatever is there first
            old_equipment = get_equipped_in_slot(self.slot)
            if old_equipment is not None:
                old_equipment.dequip()
 
            #equip object and show a message about it
            self.is_equipped = True
            message('Equipped ' + self.owner.name + ' on ' + self.slot + '.', libtcod.light_green)
        else:
            message('Equipping ' + self.owner.name + 'requires you to be level ' + str(self.required_level))
 
    def dequip(self):
        #dequip object and show a message about it
        if not self.is_equipped: return
        self.is_equipped = False
        message('Dequipped ' + self.owner.name + ' from ' + self.slot + '.', libtcod.light_yellow)

def get_equipped_in_slot(slot):  #returns the equipment in a slot, or None if it's empty
    for obj in inventory:
        if obj.equipment and obj.equipment.slot == slot and obj.equipment.is_equipped:
            return obj.equipment
    return None

def get_all_equipped(obj):  #returns a list of equipped items
    if obj == player:
        equipped_list = []
        for item in inventory:
            if item.equipment and item.equipment.is_equipped:
                equipped_list.append(item.equipment)
        return equipped_list
    else:
        return []  #other objects have no equipment
 
def is_blocked(x, y):
    #first test the map tile
    if map[x][y].blocked:
        return True
 
    #now check for any blocking objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True
 
    return False
 
def create_room(room):
    global map
    #go through the tiles in the rectangle and make them passable
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
            map[x][y].blocked = False
            map[x][y].block_sight = False

def carve_cave(room):
    global map
    #go through the tiles in the rectangle and make them passable
    for x in range(room.x1 + 1, room.x2 - 2):
        for y in range(room.y1 + 1, room.y2 - 2):
            filled_chance = libtcod.random_get_int(0, 0, 100)
            if filled_chance < 50:
                map[x][y].blocked = False
                map[x][y].block_sight = False
            else:
                map[x][y].blocked = True
                map[x][y].block_sight = True

    for x in range(room.x1 + 1, room.x2 - 2):
        for y in range(room.y1 + 1, room.y2 - 2):
            if map[x][y].blocked is False and map[x-1][y].blocked is True and map[x][y-1].blocked is True or map[x][y].blocked is False and map[x+1][y].blocked is True and map[x][y+1].blocked is True:
                map[x-1][y].blocked = False
                map[x][y-1].blocked = False
                map[x+1][y].blocked = False
                map[x][y+1].blocked = False

                map[x-1][y].block_sight = False
                map[x][y-1].block_sight = False
                map[x+1][y].block_sight = False
                map[x][y+1].block_sight = False

    (start_space_x,start_space_y) = room.center()
    map[start_space_x][start_space_y].blocked = False
    map[start_space_x][start_space_y].block_sight = False

def create_h_tunnel(x1, x2, y):
    global map
    #horizontal tunnel. min() and max() are used in case x1>x2
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False
 
def create_v_tunnel(y1, y2, x):
    global map
    #vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False
 
def make_map():
    global map, objects, stairs, dungeon_level, upstairs
 
    #the list of objects with just the player
    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
 
    rooms = []
    num_rooms = 0
 
    for r in range(MAX_ROOMS):
        #random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
 
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
 
        if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
            create_room(new_room)
 
            #add some contents to this room, such as monsters
            place_objects(new_room)
 
            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()
 
            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y

                if dungeon_level > 1:
                    #create up stairs at the point that the player starts the level.
                    upstairs = Object(new_x, new_y, '>', 'upstairs', libtcod.white)
                    objects.append(upstairs)

            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)
 
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

    #create down stairs at the center of the last room
    stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white)
    objects.append(stairs)
    stairs.send_to_back()  #so it's drawn below the monsters

def make_map_going_up():
    global map, objects, stairs, dungeon_level, upstairs
 
    #the list of objects with just the player
    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
 
    rooms = []
    num_rooms = 0
 
    for r in range(MAX_ROOMS):
        #random width and height
        w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
 
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
 
        if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
            create_room(new_room)
 
            #add some contents to this room, such as monsters
            place_objects(new_room)
 
            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()
 
            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y

                if dungeon_level > 1:
                    #create up stairs at the point that the player starts the level.
                    stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white)
                    objects.append(stairs)
                    stairs.send_to_back()

            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)
 
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

    #create down stairs at the center of the last room
    upstairs = Object(new_x, new_y, '<', 'upstairs', libtcod.white)
    objects.append(upstairs)
    upstairs.send_to_back()  #so it's drawn below the monsters

def make_initial_map():
    global map, objects, stairs, dungeon_level
 
    #the list of objects with just the player
    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
       
    w = 12
    h = 12
    
    x = 34
    y = 15
 
    #"Rect" class makes rectangles easier to work with
    new_room = Rect(x, y, w, h)
 
    create_room(new_room)
 
    #center coordinates of new room, will be useful later
    (new_x, new_y) = new_room.center()
 
    player.x = new_x
    player.y = new_y


    #create down stairs at the center of the last room
    stairs = Object(new_x+1, new_y+1, '<', 'stairs', libtcod.white)
    objects.append(stairs)
    stairs.send_to_back()  #so it's drawn below the monsters

   
def make_cave_map():
    global map, objects, stairs, dungeon_level, upstairs
 
    #the list of objects with just the player
    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
 
    rooms = []
    num_rooms = 0
 
    for r in range(MAX_CAVES):
        #random width and height
        w = libtcod.random_get_int(0, CAVE_MIN_SIZE, CAVE_MAX_SIZE)
        h = libtcod.random_get_int(0, CAVE_MIN_SIZE, CAVE_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
 
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
 
        if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
            carve_cave(new_room)
 
            #add some contents to this room, such as monsters
            place_objects(new_room)
 
            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()
 
            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y

                if dungeon_level > 1:
                    #create up stairs at the point that the player starts the level.
                    upstairs = Object(new_x, new_y, '<', 'upstairs', libtcod.white)
                    objects.append(upstairs)
                    upstairs.send_to_back()

            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)
 
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

    #create down stairs at the center of the last room
    stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white)
    objects.append(stairs)
    stairs.send_to_back()

def make_cave_map_going_up():
    global map, objects, stairs, dungeon_level, upstairs
 
    #the list of objects with just the player
    objects = [player]
 
    #fill map with "blocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]
 
    rooms = []
    num_rooms = 0
 
    for r in range(MAX_CAVES):
        #random width and height
        w = libtcod.random_get_int(0, CAVE_MIN_SIZE, CAVE_MAX_SIZE)
        h = libtcod.random_get_int(0, CAVE_MIN_SIZE, CAVE_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
        y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)
 
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break
 
        if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
            carve_cave(new_room)
 
            #add some contents to this room, such as monsters
            place_objects(new_room)
 
            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()
 
            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y

                if dungeon_level > 1:
                    #create up stairs at the point that the player starts the level.
                    stairs = Object(new_x, new_y, '<', 'stairs', libtcod.white)
                    objects.append(upstairs)
                    stairs.send_to_back()

            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
                if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)
 
            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

    #create down stairs at the center of the last room
    upstairs = Object(new_x, new_y, '<', 'stairs', libtcod.white)
    objects.append(stairs)
    upstairs.send_to_back()



def random_choice_index(chances):  #choose one option from list of chances, returning its index
    #the dice will land on some number between 1 and the sum of the chances
    dice = libtcod.random_get_int(0, 1, sum(chances))
 
    #go through all chances, keeping the sum so far
    running_sum = 0
    choice = 0
    for w in chances:
        running_sum += w
 
        #see if the dice landed in the part that corresponds to this choice
        if dice <= running_sum:
            return choice
        choice += 1

def random_choice(chances_dict):
    #choose one option from dictionary of chances, returning its key
    chances = chances_dict.values()
    strings = chances_dict.keys()
 
    return strings[random_choice_index(chances)]

def from_dungeon_level(table):
    #returns a value that depends on level. the table specifies what value occurs after each level, default is 0.
    for (value, level) in reversed(table):
        if dungeon_level >= level:
            return value
    return 0

def place_objects(room):
    #this is where we decide the chance of each monster or item appearing.
 
    #maximum number of monsters per room
    """In the tables here, [2,1] for example, the first number is the value and
    the second number is the dungeon level"""
    max_monsters = from_dungeon_level([[2, 1], [2, 2], [2, 3], [3, 4], [3, 5], [5, 6], [5, 7], [6, 8], [7, 9], [20, 10], [25, 11], [30, 12], [35, 13]])
 
    #chance of each monster
    """Using the table pairs I can make it so that monsters only show up at certain points
    I'm not sure if the jump from three to five in the troll example below means that a troll
    will not appear on level four, or if level four will have the same settings as level three
    Playing around with it should be easy enough."""
    monster_chances = {}
    monster_chances['void rat'] = 80
    monster_chances['orc'] = from_dungeon_level([[5,1],[10,2],[15,3],[20,4],[25,5],[35,6],[40,7],[40,8],[40,9],[50,10],[50,11],[60,12],[70,13]])
    monster_chances['troll'] = from_dungeon_level([[5,3],[5,4],[10,5],[15,6],[20,7],[25,8],[30,9],[40,10],[50,11],[60,12],[70,13]])
    monster_chances['rickety skeleton'] = 30
    monster_chances['kobold fighter'] = from_dungeon_level([[60,3],[90,6]])
 
    #maximum number of items per room
    max_items = from_dungeon_level([[1, 1], [2, 6]])
 
    #chance of each item (by default they have a chance of 0 at level 1, which then goes up)
    item_chances = {}
    item_chances['heal'] = 30  #healing potion always shows up, even if all other items have 0 chance
    item_chances['poison'] = 4  #poison potion always shows up, even if all other items have 0 chance
    item_chances['lightning'] = from_dungeon_level([[5, 4]])
    item_chances['fireball'] = from_dungeon_level([[5, 6]])
    item_chances['confuse'] = from_dungeon_level([[4,2]])
    item_chances['short sword'] = from_dungeon_level([[7, 4],[1,5],[0,8]])
    item_chances['small shield'] = from_dungeon_level([[10, 3],[1,5],[0,8]])
    item_chances['war hammer'] = from_dungeon_level([[3,6],[0,7],[1,8],[0,9]])
    item_chances['champions shield'] = from_dungeon_level([[2, 7],[8,8],[1,10]])
    item_chances['padded leather armor'] = from_dungeon_level([[2, 2],[10,4],[1,5]])
    item_chances['leather skullcap'] = from_dungeon_level([[3,2],[1,3]])
    item_chances['broken dagger'] = from_dungeon_level([[7,1],[1,2]])
    item_chances['tarnished golden ring'] = from_dungeon_level([[5,2],[0,3]])
 
 
    #choose random number of monsters
    num_monsters = libtcod.random_get_int(0, 0, max_monsters)
 
    for i in range(num_monsters):
        #choose random spot for this monster
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
 
        #only place it if the tile is not blocked
        if not is_blocked(x, y):
            choice = random_choice(monster_chances)
            if choice == 'orc':
                #create an orc
                fighter_component = Fighter(hp=25, defense=2, power=4, lore=0, xp=35, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'o', 'orc', libtcod.darker_green,
                    blocks=True, fighter=fighter_component, ai=ai_component)
 
            elif choice == 'troll':
                #create a troll
                fighter_component = Fighter(hp=40, defense=4, power=8, lore=0, xp=100, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'T', 'troll', libtcod.darker_green,
                    blocks=True, fighter=fighter_component, ai=ai_component)

            elif choice == 'void rat':
                #create a void rat
                fighter_component = Fighter(hp=10, defense=0, power=0, lore=0, xp=15, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'r', 'void rat', libtcod.dark_chartreuse,
                    blocks=True, fighter=fighter_component, ai=ai_component)
            elif choice == 'rickety skeleton':
                #create a void rat
                fighter_component = Fighter(hp=14, defense=1, power=1, lore=0, xp=15, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 's', 'rickety skeleton', libtcod.dark_chartreuse,
                    blocks=True, fighter=fighter_component, ai=ai_component)

            elif choice == 'kobold fighter':
                #create a void rat
                fighter_component = Fighter(hp=20, defense=1, power=2, lore=0, xp=20, death_function=monster_death)
                ai_component = BasicMonster()
 
                monster = Object(x, y, 'k', 'kobold fighter', libtcod.dark_chartreuse,
                    blocks=True, fighter=fighter_component, ai=ai_component)
 
            objects.append(monster)
 
    #choose random number of items
    num_items = libtcod.random_get_int(0, 0, max_items)
 
    for i in range(num_items):
        #choose random spot for this item
        x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
        y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
 
        #only place it if the tile is not blocked
        if not is_blocked(x, y):
            choice = random_choice(item_chances)
            if choice == 'heal':
                #create a healing potion
                item_component = Item(use_function=cast_heal)
                item = Object(x, y, '!', 'violet potion', libtcod.violet, item=item_component)

            elif choice == 'poison':
                #create a healing potion
                item_component = Item(use_function=cast_poison)
                item = Object(x, y, '!', 'violet potion', libtcod.violet, item=item_component)
 
            elif choice == 'lightning':
                #create a lightning bolt scroll
                item_component = Item(use_function=cast_lightning)
                item = Object(x, y, '#', 'scroll of lightning bolt', libtcod.light_yellow, item=item_component)
 
            elif choice == 'fireball':
                #create a fireball scroll
                item_component = Item(use_function=cast_fireball)
                item = Object(x, y, '#', 'scroll of fireball', libtcod.light_yellow, item=item_component)
 
            elif choice == 'confuse':
                #create a confuse scroll
                item_component = Item(use_function=cast_confuse)
                item = Object(x, y, '#', 'scroll of confusion', libtcod.light_yellow, item=item_component)

            elif choice == 'short sword':
                #create a sword
                equipment_component = Equipment(slot='right hand', power_bonus=2, required_level=3)
                item = Object(x, y, '&', 'short sword', libtcod.sky, equipment=equipment_component)

            elif choice == 'small shield':
                #create a shield
                equipment_component = Equipment(slot='left hand', defense_bonus=1, required_level=2)
                item = Object(x, y, '&', 'small shield', libtcod.orange, equipment=equipment_component)

            elif choice == 'war hammer':
                #create a sword
                equipment_component = Equipment(slot='right hand', power_bonus=3, defense_bonus=-1, required_level=5)
                item = Object(x, y, '&', 'war hammer', libtcod.sky, equipment=equipment_component)

            elif choice == 'champions shield':
                #create a shield
                equipment_component = Equipment(slot='left hand', defense_bonus=3, required_level=6)
                item = Object(x, y, '&', 'champions shield', libtcod.orange, equipment=equipment_component)

            elif choice == 'padded leather armor':
                #create a shield
                equipment_component = Equipment(slot='body', defense_bonus=2, required_level=2)
                item = Object(x, y, '&', 'padded leather armor', libtcod.orange, equipment=equipment_component)

            elif choice == 'leather skullcap':
                #create a shield
                equipment_component = Equipment(slot='head', defense_bonus=1, required_level=1)
                item = Object(x, y, '&', 'leather skullcap', libtcod.orange, equipment=equipment_component)

            elif choice == 'broken dagger':
                #create a shield
                equipment_component = Equipment(slot='right hand', required_level=1)
                item = Object(x, y, '&', 'broken dagger', libtcod.orange, equipment=equipment_component)

            elif choice == 'tarnished golden ring':
                #create a shield
                equipment_component = Equipment(slot='right ring finger', lore_bonus=2, required_level=3)
                item = Object(x, y, '*', 'tarnished golden ring', libtcod.gold, equipment=equipment_component)
 
            objects.append(item)
            item.send_to_back()  #items appear below other objects
            item.always_visible = True  #items are visible even out-of-FOV, if in an explored area
 
 
def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    #render a bar (HP, experience, etc). first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)
 
    #render the background first
    libtcod.console_set_default_background(panel, back_color)
    libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
 
    #now render the bar on top
    libtcod.console_set_default_background(panel, bar_color)
    if bar_width > 0:
        libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
 
    #finally, some centered text with the values
    libtcod.console_set_default_foreground(panel, libtcod.white)
    libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER,
        name + ': ' + str(value) + '/' + str(maximum))
 
def get_names_under_mouse():
    global mouse
 
    #return a string with the names of all objects under the mouse
    (x, y) = (mouse.cx, mouse.cy)
    (x, y) = (camera_x + x, camera_y + y)  #from screen to map coordinates
 
    #create a list with the names of all objects at the mouse's coordinates and in FOV
    names = [obj.name for obj in objects
        if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
 
    names = ', '.join(names)  #join the names, separated by commas
    return names.capitalize()
 
def move_camera(target_x, target_y):
    global camera_x, camera_y, fov_recompute
 
    #new camera coordinates (top-left corner of the screen relative to the map)
    x = target_x - CAMERA_WIDTH / 2  #coordinates so that the target is at the center of the screen
    y = target_y - CAMERA_HEIGHT / 2
 
    #make sure the camera doesn't see outside the map
    if x < 0: x = 0
    if y < 0: y = 0
    if x > MAP_WIDTH - CAMERA_WIDTH - 1: x = MAP_WIDTH - CAMERA_WIDTH - 1
    if y > MAP_HEIGHT - CAMERA_HEIGHT - 1: y = MAP_HEIGHT - CAMERA_HEIGHT - 1
 
    if x != camera_x or y != camera_y: fov_recompute = True
 
    (camera_x, camera_y) = (x, y)
 
def to_camera_coordinates(x, y):
    #convert coordinates on the map to coordinates on the screen
    (x, y) = (x - camera_x, y - camera_y)
 
    if (x < 0 or y < 0 or x >= CAMERA_WIDTH or y >= CAMERA_HEIGHT):
        return (None, None)  #if it's outside the view, return nothing
 
    return (x, y)
 
def render_all():
    global fov_map, color_dark_wall, color_light_wall
    global color_dark_ground, color_light_ground
    global fov_recompute
 
    move_camera(player.x, player.y)
 
    if fov_recompute:
        #recompute FOV if needed (the player moved or something)
        fov_recompute = False
        libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)
        libtcod.console_clear(con)
 
        #go through all tiles, and set their background color according to the FOV
        for y in range(CAMERA_HEIGHT):
            for x in range(CAMERA_WIDTH):
                (map_x, map_y) = (camera_x + x, camera_y + y)
                visible = libtcod.map_is_in_fov(fov_map, map_x, map_y)
 
                wall = map[map_x][map_y].block_sight
                if not visible:
                    #if it's not visible right now, the player can only see it if it's explored
                    if map[map_x][map_y].explored:
                        if wall:
                            libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
                        else:
                            libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
                else:
                    #it's visible
                    if wall:
                        libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET )
                    else:
                        libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET )
                    #since it's visible, explore it
                    map[map_x][map_y].explored = True
 
    #draw all objects in the list, except the player. we want it to
    #always appear over all other objects! so it's drawn later.
    for object in objects:
        if object != player:
            object.draw()
    player.draw()
 
    #blit the contents of "con" to the root console
    libtcod.console_blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT, 0, 0, 0)
 
 
    #prepare to render the GUI panel
    libtcod.console_set_default_background(panel, libtcod.black)
    libtcod.console_clear(panel)
 
    #print the game messages, one line at a time
    y = 1
    for (line, color) in game_msgs:
        libtcod.console_set_default_foreground(panel, color)
        libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
        y += 1
 
    #show the player's stats
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
        libtcod.light_red, libtcod.darker_red)

    #Show the current level
    libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Dungeon level ' + str(dungeon_level))
 
    #display names of objects under the mouse
    libtcod.console_set_default_foreground(panel, libtcod.light_gray)
    libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
 
    #blit the contents of "panel" to the root console
    libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
 
 
def message(new_msg, color = libtcod.white):
    #split the message if necessary, among multiple lines
    new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
 
    for line in new_msg_lines:
        #if the buffer is full, remove the first line to make room for the new one
        if len(game_msgs) == MSG_HEIGHT:
            del game_msgs[0]
 
        #add the new line as a tuple, with the text and the color
        game_msgs.append( (line, color) )
 
 
def player_move_or_attack(dx, dy):
    global fov_recompute
 
    #the coordinates the player is moving to/attacking
    x = player.x + dx
    y = player.y + dy
 
    #try to find an attackable object there
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break
 
    #attack if target found, move otherwise
    if target is not None:
        player.fighter.attack(target)
    else:
        player.move(dx, dy)
        fov_recompute = True
 
 
def menu(header, options, width):
    if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options.')
 
    #calculate total height for the header (after auto-wrap) and one line per option
    header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
    if header == '':
        header_height = 0
    height = len(options) + header_height
 
    #create an off-screen console that represents the menu's window
    window = libtcod.console_new(width, height)
 
    #print the header, with auto-wrap
    libtcod.console_set_default_foreground(window, libtcod.white)
    libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
 
    #print all the options
    y = header_height
    letter_index = ord('a')
    for option_text in options:
        text = '(' + chr(letter_index) + ') ' + option_text
        libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
        y += 1
        letter_index += 1
 
    #blit the contents of "window" to the root console
    x = SCREEN_WIDTH/2 - width/2
    y = SCREEN_HEIGHT/2 - height/2
    libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
 
    #present the root console to the player and wait for a key-press
    libtcod.console_flush()
    key = libtcod.console_wait_for_keypress(True)
    if key.vk == libtcod.KEY_ENTER and key.lalt:  #(special case) Alt+Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
 
    #convert the ASCII code to an index; if it corresponds to an option, return it
    index = key.c - ord('a')
    if index >= 0 and index < len(options): return index
    return None
 
def inventory_menu(header):
    #show a menu with each item of the inventory as an option
    if len(inventory) == 0:
        options = ['You are not carrying anything.']
    else:
        options = []
        for item in inventory:
            text = item.name
            #show additional information, in case it's equipped
            if item.equipment and item.equipment.is_equipped:
                text = text + ' (on ' + item.equipment.slot + ')'
            options.append(text)
 
    index = menu(header, options, INVENTORY_WIDTH)
 
    #if an item was chosen, return it
    if index is None or len(inventory) == 0: return None
    return inventory[index].item
 
def msgbox(text, width=50):
    menu(text, [], width)  #use menu() as a sort of "message box"
 
def handle_keys():
    global key
 
    if key.vk == libtcod.KEY_ENTER and key.lalt:
        #Alt+Enter: toggle fullscreen
        libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
 
    elif key.vk == libtcod.KEY_ESCAPE:
        return 'exit'  #exit game
 
    if game_state == 'playing':
        #movement keys
        if key.vk == libtcod.KEY_UP or key.vk == libtcod.KEY_KP8:
            player_move_or_attack(0, -1)
        elif key.vk == libtcod.KEY_DOWN or key.vk == libtcod.KEY_KP2:
            player_move_or_attack(0, 1)
        elif key.vk == libtcod.KEY_LEFT or key.vk == libtcod.KEY_KP4:
            player_move_or_attack(-1, 0)
        elif key.vk == libtcod.KEY_RIGHT or key.vk == libtcod.KEY_KP6:
            player_move_or_attack(1, 0)
        elif key.vk == libtcod.KEY_HOME or key.vk == libtcod.KEY_KP7:
            player_move_or_attack(-1, -1)
        elif key.vk == libtcod.KEY_PAGEUP or key.vk == libtcod.KEY_KP9:
            player_move_or_attack(1, -1)
        elif key.vk == libtcod.KEY_END or key.vk == libtcod.KEY_KP1:
            player_move_or_attack(-1, 1)
        elif key.vk == libtcod.KEY_PAGEDOWN or key.vk == libtcod.KEY_KP3:
            player_move_or_attack(1, 1)
        elif key.vk == libtcod.KEY_KP5:
            pass  #do nothing ie wait for the monster to come to you, possibly associate a regen hp here.

        else:
            #test for other keys
            key_char = chr(key.c)
 
            if key_char == 'g':
                #pick up an item
                for object in objects:  #look for an item in the player's tile
                    if object.x == player.x and object.y == player.y and object.item:
                        object.item.pick_up()
                        break
 
            if key_char == 'i':
                #show the inventory; if an item is selected, use it
                chosen_item = inventory_menu('Press the key next to an item to use it, or any other to cancel.\n')
                if chosen_item is not None:
                    chosen_item.use()
 
            if key_char == 'd':
                #show the inventory; if an item is selected, drop it
                chosen_item = inventory_menu('Press the key next to an item to drop it, or any other to cancel.\n')
                if chosen_item is not None:
                    chosen_item.drop()

            if key_char == 'c':
                #show character information
                level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
                msgbox('Character Information\n\nLevel: ' + str(player.level) + '\nExperience: ' + str(player.fighter.xp) +
                    '\nExperience to level up: ' + str(level_up_xp) + '\n\nMaximum HP: ' + str(player.fighter.max_hp) +
                    '\nAttack: ' + str(player.fighter.power) + '\nDefense: ' + str(player.fighter.defense) + '\nLore: ' + str(player.fighter.lore), CHARACTER_SCREEN_WIDTH)

            if key_char == 'h':
                #show the controls
                msgbox("Controls:\n\n\ng - Pick Up Item\n\ni - View Inventory & Use or Equip Items\n\nd - Drop Item\n\nc - View Player Stats\n\n< - Go Down Stairs\n\n> - Go Up Stairs\n\nh - View Command List\n\nEsc - Bring Up Game Menu\n\nAlt+Enter - Toggle Full Screen\n\n\nEquip items from the inventory screen. Automatic de-equippping occurs if an item already occupies the slot you are trying to equip to.", CHARACTER_SCREEN_WIDTH)

            if key_char == '<':
                #go down stairs, if the player is on them
                if stairs.x == player.x and stairs.y == player.y:
                    next_level()

            if key_char == '>':
                #go up stairs, if the player is on them
                if upstairs.x == player.x and upstairs.y == player.y:
                    previous_level()
 
            return 'didnt-take-turn'
 
def check_level_up():
        #see if the player's experience is enough to level-up
        level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
        if player.fighter.xp >= level_up_xp:
            player.level += 1
            player.fighter.xp -= level_up_xp
            player.fighter.hp = player.fighter.max_hp
            # Change this message to something more game world appropriate:
            message('Your battle skills grow stronger! You reached level ' + str(player.level) + '!', libtcod.yellow)

            choice = None
            while choice == None:  #keep asking until a choice is made
                choice = menu('Level up! Choose a stat to raise:\n',
                    ['Constitution (+20 HP, from ' + str(player.fighter.max_hp) + ')',
                    'Strength (+1 attack, from ' + str(player.fighter.power) + ')',
                    'Agility (+1 defense, from ' + str(player.fighter.defense) + ')',
                    'Lore (+1 lore, from ' + str(player.fighter.lore) + ')'], LEVEL_SCREEN_WIDTH)
 
            if choice == 0:
                player.fighter.base_max_hp += 20
                player.fighter.hp += 20
            elif choice == 1:
                player.fighter.base_power += 1
            elif choice == 2:
                player.fighter.base_defense += 1
            elif choice == 3:
                player.fighter.base_lore += 1

def player_death(player):
    #the game ended!
    global game_state
    message('You died!', libtcod.red)
    game_state = 'dead'
 
    #for added effect, transform the player into a corpse!
    player.char = '%'
    player.color = libtcod.dark_red
 
def monster_death(monster):
    #transform it into a nasty corpse! it doesn't block, can't be
    #attacked and doesn't move
    message('The ' + monster.name + ' is dead! You gain ' + str(monster.fighter.xp) + ' experience.', libtcod.orange)
    monster.char = '%'
    monster.color = libtcod.dark_red
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = 'remains of ' + monster.name
    monster.send_to_back()
 
def target_tile(max_range=None):
    #return the position of a tile left-clicked in player's FOV (optionally in a range), or (None,None) if right-clicked.
    global key, mouse
    while True:
        #render the screen. this erases the inventory and shows the names of objects under the mouse.
        libtcod.console_flush()
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse) 
        render_all()
        (x, y) = (mouse.cx, mouse.cy)
        (x, y) = (camera_x + x, camera_y + y)  #from screen to map coordinates
 
        if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
            return (None, None)  #cancel if the player right-clicked or pressed Escape
 
        #accept the target if the player clicked in FOV, and in case a range is specified, if it's in that range
        if (mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y) and
            (max_range is None or player.distance(x, y) <= max_range)):
            return (x, y)
 
def target_monster(max_range=None):
    #returns a clicked monster inside FOV up to a range, or None if right-clicked
    while True:
        (x, y) = target_tile(max_range)
        if x is None:  #player cancelled
            return None
 
        #return the first clicked monster, otherwise continue looping
        for obj in objects:
            if obj.x == x and obj.y == y and obj.fighter and obj != player:
                return obj
 
def closest_monster(max_range):
    #find closest enemy, up to a maximum range, and in the player's FOV
    closest_enemy = None
    closest_dist = max_range + 1  #start with (slightly more than) maximum range
 
    for object in objects:
        if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
            #calculate distance between this object and the player
            dist = player.distance_to(object)
            if dist < closest_dist:  #it's closer, so remember it
                closest_enemy = object
                closest_dist = dist
    return closest_enemy
 
def cast_poison():
    #poison the player
    poison_amount = libtcod.random_get_int(0, 5, 20)
    message('The poition was poisoned, you take '+str(poison_amount)+' poison damage!', libtcod.red)
    player.fighter.heal(poison_amount)

def cast_heal():
    #heal the player
    if player.fighter.hp == player.fighter.max_hp:
        message('You are already at full health.', libtcod.red)
        return 'cancelled'
    heal_amount = libtcod.random_get_int(0, 10, 40)
    message('Your wounds start to feel better!', libtcod.light_violet)
    player.fighter.heal(heal_amount)
 
def cast_lightning():
    if player.fighter.lore >= 2:
        #find closest enemy (inside a maximum range) and damage it
        monster = closest_monster(LIGHTNING_RANGE)
        if monster is None:  #no enemy found within maximum range
            message('No enemy is close enough to strike.', libtcod.red)
            return 'cancelled'
 
        #zap it!
        message('A lighting bolt strikes the ' + monster.name + ' with a loud thunder! The damage is '
            + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
        monster.fighter.take_damage(LIGHTNING_DAMAGE)
    else:
        message('You are not learned enough to cast this spell.', libtcod.red)
        return 'cancelled'
 
def cast_fireball():
    if player.fighter.lore >= 3:
        #ask the player for a target tile to throw a fireball at
        message('Left-click a target tile for the fireball, or right-click to cancel.', libtcod.light_cyan)
        (x, y) = target_tile()
        if x is None: return 'cancelled'
        message('The fireball explodes, burning everything within ' + str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)
 
        for obj in objects:  #damage every fighter in range, including the player
            if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
                message('The ' + obj.name + ' gets burned for ' + str(FIREBALL_DAMAGE) + ' hit points.', libtcod.orange)
                obj.fighter.take_damage(FIREBALL_DAMAGE)
    else:
        message('You are not learned enough to cast this spell.', libtcod.red)
        return 'cancelled'
 
def cast_confuse():
    if player.fighter.lore >= 1:
        #ask the player for a target to confuse
        message('Left-click an enemy to confuse it, or right-click to cancel.', libtcod.light_cyan)
        monster = target_monster(CONFUSE_RANGE)
        if monster is None: return 'cancelled'
 
        #replace the monster's AI with a "confused" one; after some turns it will restore the old AI
        old_ai = monster.ai
        monster.ai = ConfusedMonster(old_ai)
        monster.ai.owner = monster  #tell the new component who owns it
        message('The eyes of the ' + monster.name + ' look vacant, as he starts to stumble around!', libtcod.light_green)
    else:
        message('You are not learned enough to cast this spell.', libtcod.red)
        return 'cancelled'
        
 
def save_game():
    #open a new empty shelve (possibly overwriting an old one) to write the game data
    file = shelve.open('savegame', 'n')
    file['map'] = map
    file['objects'] = objects
    file['player_index'] = objects.index(player)  #index of player in objects list
    file['inventory'] = inventory
    file['game_msgs'] = game_msgs
    file['game_state'] = game_state
    file['stairs_index'] = objects.index(stairs)
    file['upstairs_index'] = objects.index(upstairs)
    file['dungeon_level'] = dungeon_level
    file.close()
 
def load_game():
    #open the previously saved shelve and load the game data
    global map, objects, player, stairs, inventory, game_msgs, game_state, dungeon_level, upstairs
 
    file = shelve.open('savegame', 'r')
    map = file['map']
    objects = file['objects']
    player = objects[file['player_index']]  #get index of player in objects list and access it
    inventory = file['inventory']
    game_msgs = file['game_msgs']
    game_state = file['game_state']
    stairs = objects[file['stairs_index']]
    upstairs = objects[file['upstairs_index']]
    dungeon_level = file['dungeon_level']
    file.close()
 
    initialize_fov()
 
def new_game():
    global player, inventory, game_msgs, game_state, dungeon_level
 
    #create object representing the player
    """This houses the starting player stats"""
    fighter_component = Fighter(hp=100, defense=0, power=0, lore=0, xp = 0, death_function=player_death)
    player = Object(0, 0, '@', 'player', libtcod.white, blocks=True, fighter=fighter_component)

    player.level = 1
 
    #generate map (at this point it's not drawn to the screen)
    dungeon_level = 10
    make_initial_map()
    initialize_fov()
 
    game_state = 'playing'
    inventory = []
 
    #create the list of game messages and their colors, starts empty
    game_msgs = []
 
    #a warm welcoming message!
    message('You have awakened in a room, with no memory of how you got there. There are stairs leading down.', libtcod.red)

    #initial equipment: a dagger
    equipment_component = Equipment(slot='right hand', power_bonus=1)
    obj = Object(0, 0, '-', 'dagger', libtcod.sky, equipment=equipment_component)
    inventory.append(obj)
    equipment_component.equip()
    obj.always_visible = True

def next_level():
    global dungeon_level, MAX_ROOMS, MAP_HEIGHT, MAP_WIDTH

    #save the state of the first level
    if dungeon_level < 2:
        file = shelve.open('persistence1', 'n')
        file['map'] = map
        file['objects'] = objects
        file['player_index'] = objects.index(player)
        file['stairs_index'] = objects.index(stairs)
        file.close

    #advance to the next level
    dungeon_level += 1
    message('You descend deeper into the heart of the dungeon...', libtcod.red)
    if dungeon_level < 10:
        MAX_ROOMS *= 1.5
        MAX_ROOMS = int(round(MAX_ROOMS))
        MAP_WIDTH += 10
        MAP_HEIGHT += 10
        make_map()  #create a new level
        initialize_fov()
    else:
        make_cave_map() #create a new cave level
        initialize_fov()

def previous_level():
    global dungeon_level, map, objects, player, stairs, MAX_ROOMS, MAP_HEIGHT, MAP_WIDTH

    #advance to the next level
    dungeon_level -= 1
    
    if dungeon_level > 1 and dungeon_level < 10:
        MAX_ROOMS /= 1.5
        MAX_ROOMS = int(round(MAX_ROOMS))
        MAP_WIDTH -= 10
        MAP_HEIGHT -= 10
        make_map_going_up()  #generate a new higher level!
        initialize_fov()
        message('You climb up to a higher dungeon level...', libtcod.red)
    elif dungeon_level > 9:
        make_cave_map_going_up()  #generate a new higher level!
        initialize_fov()
        message('You climb up to a higher dungeon level...', libtcod.red)
    else:
        file = shelve.open('stats', 'n')
        file['hp'] = player.fighter.hp
        file['xp'] = player.fighter.xp
        file['lore'] = player.fighter.lore
        file['power'] = player.fighter.power
        file['defense'] = player.fighter.defense
        file['level'] = player.level
        file['max_hp'] = player.fighter.max_hp
        file.close

        make_initial_map()
         
        file = shelve.open('persistence1', 'r')
        map = file['map']
        objects = file['objects']
        player = objects[file['player_index']]
        stairs = objects[file['stairs_index']]
        file.close

        file = shelve.open('stats', 'r')
        player.fighter.hp = file['hp']
        player.fighter.xp = file['xp']
        player.fighter.lore = file['lore']
        player.fighter.power = file['power']
        player.fighter.defense = file['defense']
        player.level = file['level']
        player.fighter.max_hp = file['max_hp']
        file.close

        initialize_fov()  
        message('You enjoy a rare moment of peace in an issolated place...', libtcod.light_violet)


def initialize_fov():
    global fov_recompute, fov_map
    fov_recompute = True
 
    #create the FOV map, according to the generated map
    fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            libtcod.map_set_properties(fov_map, x, y, not map[x][y].blocked, not map[x][y].block_sight)
 
    libtcod.console_clear(con)  #unexplored areas start black (which is the default background color)
 
def play_game():
    global camera_x, camera_y, key, mouse
 
    player_action = None
    mouse = libtcod.Mouse()
    key = libtcod.Key()
 
    (camera_x, camera_y) = (0, 0)
 
    while not libtcod.console_is_window_closed():
        #render the screen
        libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
        render_all()
 
        libtcod.console_flush()

        check_level_up()
 
        #erase all objects at their old locations, before they move
        for object in objects:
            object.clear()
 
        #handle keys and exit game if needed
        player_action = handle_keys()
        if player_action == 'exit':
            save_game()
            break
 
        #let monsters take their turn
        if game_state == 'playing' and player_action != 'didnt-take-turn':
            for object in objects:
                if object.ai:
                    object.ai.take_turn()
 
def main_menu():
    #This is the background image. It needs to be double the screen w/h dimensions in pixels (80x50 becomes 160x100)
    img = libtcod.image_load('menubackground.png')
 
    while not libtcod.console_is_window_closed():
        #show the background image, at twice the regular console resolution
        libtcod.image_blit_2x(img, 0, 0, 0)
 
        #show the game's title, and some credits!
        libtcod.console_set_default_foreground(0, libtcod.light_yellow)
        libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT/2-4, libtcod.BKGND_NONE, libtcod.CENTER, 'Castles and Catacombs')
        libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT-2, libtcod.BKGND_NONE, libtcod.LEFT, 'A game by Brian Evans')
 
        #show options and wait for the player's choice
        choice = menu('', ['Begin the search', 'Resume your search', 'Quit'], 25)
        if choice == 0:  #new game
            new_game()
            play_game()
        if choice == 1:  #load last game
            try:
                load_game()
            except:
                msgbox('\n No saved game to load.\n', 24)
                continue
            play_game()
        elif choice == 2:  #quit
            break
 
libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'Chale & the Voidmen', False)
libtcod.sys_set_fps(LIMIT_FPS)
con = libtcod.console_new(MAP_WIDTH, MAP_HEIGHT)
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)
 
main_menu()
